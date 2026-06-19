import shutil
import threading
import uuid
from pathlib import Path
from typing import Callable, Optional


def parse_repo_id(text: str) -> str:
    """从 HuggingFace 链接或 org/model 文本中解析出 repo_id。"""
    text = (text or "").strip().rstrip("/")
    for prefix in ("https://huggingface.co/", "http://huggingface.co/", "huggingface.co/"):
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    parts = [p for p in text.split("/") if p]
    if len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    return text


class ModelManager:
    """模型只看 / 只下到 models_dir（服务自己的目录），与机器全局 HF 缓存隔离。"""

    def __init__(self, models_provider: Callable, default_model: str,
                 models_dir, hub=None, on_set_default: Optional[Callable] = None):
        self._models_provider = models_provider
        self._default_model = default_model
        self._models_dir = Path(models_dir) if models_dir else None
        self._on_set_default = on_set_default
        if hub is None:
            import huggingface_hub as hub  # lazy-load real implementation
        self._hub = hub
        self._downloads = {}             # job_id -> {status, repo_id, error}
        self._lock = threading.Lock()

    def _by_name(self, name: str):
        for info in self._models_provider():
            if info.name == name:
                return info
        raise KeyError(name)

    def _repo_path(self, repo_id: str) -> Optional[Path]:
        return (self._models_dir / repo_id) if self._models_dir else None

    def _local_repos(self) -> dict:
        """扫描 models_dir 下的 <org>/<name> 目录（含手动复制进来的），返回 repo_id -> 字节大小。"""
        base = self._models_dir
        if not base or not base.exists():
            return {}
        out = {}
        for org in base.iterdir():
            if not org.is_dir():
                continue
            for name in org.iterdir():
                if not name.is_dir():
                    continue
                size = sum(f.stat().st_size for f in name.rglob("*") if f.is_file())
                out[f"{org.name}/{name.name}"] = size
        return out

    def list(self) -> list:
        local = self._local_repos()
        rows = []
        for m in self._models_provider():
            rows.append({
                "name": m.name,
                "family": m.family,
                "repo_id": m.repo_id,
                "capabilities": m.capabilities,
                "downloaded": m.repo_id in local,
                "size_gb": local.get(m.repo_id, 0) / 1e9,
                "is_default": m.name == self._default_model,
            })
        return rows

    def list_cached(self) -> list:
        """models_dir 里所有本地模型（含手动放入的），按 repo_id 排序。"""
        return sorted(
            ({"repo_id": rid, "size_gb": size / 1e9} for rid, size in self._local_repos().items()),
            key=lambda x: x["repo_id"],
        )

    def start_download_repo(self, repo_id: str) -> str:
        """后台下载任意 HuggingFace repo_id 到 models_dir/<repo_id>，返回可轮询的 job_id。"""
        repo_id = (repo_id or "").strip()
        if not repo_id:
            raise ValueError("empty repo id")
        target = self._repo_path(repo_id)
        job_id = uuid.uuid4().hex
        with self._lock:
            self._downloads[job_id] = {"status": "running", "repo_id": repo_id, "error": None}

        def _run():
            try:
                if target is not None:
                    self._hub.snapshot_download(repo_id, local_dir=str(target))
                else:
                    self._hub.snapshot_download(repo_id)
                state, err = "done", None
            except Exception as exc:  # noqa: BLE001
                state, err = "error", str(exc) or exc.__class__.__name__
            with self._lock:
                self._downloads[job_id]["status"] = state
                self._downloads[job_id]["error"] = err

        threading.Thread(target=_run, daemon=True).start()
        return job_id

    def start_download(self, name: str) -> str:
        return self.start_download_repo(self._by_name(name).repo_id)

    def download_status(self, job_id: str) -> dict:
        with self._lock:
            return dict(self._downloads[job_id])

    def delete_repo(self, repo_id: str) -> bool:
        path = self._repo_path(repo_id)
        if path is None or not (path.exists() or path.is_symlink()):
            return False
        if path.is_symlink():
            path.unlink()            # 只删软链，不动被链接的缓存
        else:
            shutil.rmtree(path)
        return True

    def delete(self, name: str) -> bool:
        return self.delete_repo(self._by_name(name).repo_id)

    def set_default(self, name: str) -> None:
        self._by_name(name)  # validate exists, raise KeyError if not
        self._default_model = name
        if self._on_set_default is not None:
            self._on_set_default(name)
