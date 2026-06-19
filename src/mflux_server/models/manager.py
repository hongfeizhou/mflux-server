import threading
import uuid
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
    def __init__(self, models_provider: Callable, default_model: str,
                 hub=None, on_set_default: Optional[Callable] = None):
        # models_provider() -> list[ModelInfo]; hub defaults to real huggingface_hub
        self._models_provider = models_provider
        self._default_model = default_model
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

    def _cached_sizes(self) -> dict:
        info = self._hub.scan_cache_dir()
        return {repo.repo_id: repo.size_on_disk for repo in info.repos}

    def list(self) -> list:
        sizes = self._cached_sizes()
        rows = []
        for m in self._models_provider():
            size = sizes.get(m.repo_id, 0)
            rows.append({
                "name": m.name,
                "family": m.family,
                "repo_id": m.repo_id,
                "capabilities": m.capabilities,
                "downloaded": m.repo_id in sizes,
                "size_gb": size / 1e9,
                "is_default": m.name == self._default_model,
            })
        return rows

    def list_cached(self) -> list:
        """返回磁盘上所有已缓存的 repo（含任意通过链接下载的）。"""
        info = self._hub.scan_cache_dir()
        rows = [{"repo_id": r.repo_id, "size_gb": r.size_on_disk / 1e9}
                for r in info.repos]
        return sorted(rows, key=lambda x: x["repo_id"])

    def start_download_repo(self, repo_id: str) -> str:
        """后台下载任意 HuggingFace repo_id，返回可轮询的 job_id。"""
        repo_id = (repo_id or "").strip()
        if not repo_id:
            raise ValueError("empty repo id")
        job_id = uuid.uuid4().hex
        with self._lock:
            self._downloads[job_id] = {"status": "running", "repo_id": repo_id, "error": None}

        def _run():
            try:
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
        cache = self._hub.scan_cache_dir()
        hashes = []
        for repo in cache.repos:
            if repo.repo_id == repo_id:
                hashes = [rev.commit_hash for rev in repo.revisions]
        if not hashes:
            return False
        cache.delete_revisions(*hashes).execute()
        return True

    def delete(self, name: str) -> bool:
        return self.delete_repo(self._by_name(name).repo_id)

    def set_default(self, name: str) -> None:
        self._by_name(name)  # validate exists, raise KeyError if not
        self._default_model = name
        if self._on_set_default is not None:
            self._on_set_default(name)
