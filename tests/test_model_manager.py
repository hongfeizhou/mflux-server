import time
import pytest
from mflux_server.models.manager import ModelManager, parse_repo_id
from mflux_server.engines.base import ModelInfo


class _FakeHub:
    def __init__(self):
        self.calls = []

    def snapshot_download(self, repo_id, local_dir=None):
        self.calls.append((repo_id, local_dir))
        if local_dir:
            import os
            os.makedirs(local_dir, exist_ok=True)
            with open(os.path.join(local_dir, "model.safetensors"), "wb") as f:
                f.write(b"x" * 10)


def _models():
    return [ModelInfo(name="z-image-turbo", family="z-image", engine="mflux-image",
                      capabilities=["text-to-image"], repo_id="Tongyi-MAI/Z-Image-Turbo")]


def _mk(tmp_path, hub=None, **kw):
    return ModelManager(models_provider=_models, default_model="z-image-turbo",
                        models_dir=tmp_path / "models", hub=hub or _FakeHub(), **kw)


def test_parse_repo_id():
    assert parse_repo_id("https://huggingface.co/org/model") == "org/model"
    assert parse_repo_id("https://huggingface.co/org/model/tree/main") == "org/model"
    assert parse_repo_id("  org/model/  ") == "org/model"
    assert parse_repo_id("huggingface.co/a/b") == "a/b"


def test_list_not_downloaded_when_dir_empty(tmp_path):
    row = _mk(tmp_path).list()[0]
    assert row["downloaded"] is False
    assert row["size_gb"] == 0
    assert row["is_default"] is True


def test_manual_copy_shows_in_list(tmp_path):
    repo_dir = tmp_path / "models" / "Tongyi-MAI" / "Z-Image-Turbo"
    repo_dir.mkdir(parents=True)
    (repo_dir / "w.safetensors").write_bytes(b"y" * 2_000_000)
    mgr = _mk(tmp_path)
    assert mgr.list()[0]["downloaded"] is True
    cached = mgr.list_cached()
    assert cached[0]["repo_id"] == "Tongyi-MAI/Z-Image-Turbo"
    assert cached[0]["size_gb"] > 0


def test_download_goes_to_models_dir(tmp_path):
    hub = _FakeHub()
    mgr = _mk(tmp_path, hub=hub)
    job_id = mgr.start_download_repo("some/other-model")
    for _ in range(100):
        if mgr.download_status(job_id)["status"] in ("done", "error"):
            break
        time.sleep(0.02)
    assert mgr.download_status(job_id)["status"] == "done"
    repo_id, local_dir = hub.calls[-1]
    assert repo_id == "some/other-model"
    assert local_dir.replace("\\", "/").endswith("some/other-model")
    assert any(r["repo_id"] == "some/other-model" for r in mgr.list_cached())


def test_download_rejects_empty(tmp_path):
    with pytest.raises(ValueError):
        _mk(tmp_path).start_download_repo("   ")


def test_delete_repo(tmp_path):
    repo_dir = tmp_path / "models" / "a" / "one"
    repo_dir.mkdir(parents=True)
    (repo_dir / "f").write_bytes(b"z")
    mgr = _mk(tmp_path)
    assert mgr.delete_repo("a/one") is True
    assert not repo_dir.exists()
    assert mgr.delete_repo("missing/repo") is False


def test_set_default_callback(tmp_path):
    saved = []
    mgr = _mk(tmp_path, on_set_default=saved.append)
    mgr.set_default("z-image-turbo")
    assert saved == ["z-image-turbo"]
    with pytest.raises(KeyError):
        mgr.set_default("ghost")
