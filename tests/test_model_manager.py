import time
from mflux_server.models.manager import ModelManager
from mflux_server.engines.base import ModelInfo


class _FakeHub:
    def __init__(self, cached=None):
        self._cached = cached or {}     # repo_id -> size_bytes
        self.downloaded = []
        self.deleted = []

    def scan_cache_dir(self):
        hub = self

        class _Revision:
            commit_hash = "abc123"

        class _Repo:
            def __init__(self, rid, size):
                self.repo_id = rid
                self.size_on_disk = size
                self.revisions = [_Revision()]

        class _Info:
            repos = [_Repo(rid, sz) for rid, sz in hub._cached.items()]

            def delete_revisions(self, *hashes):
                class _Strategy:
                    def execute(self_inner):
                        hub.deleted.append(hashes)
                return _Strategy()
        return _Info()

    def snapshot_download(self, repo_id):
        self.downloaded.append(repo_id)
        self._cached[repo_id] = 123


def _models():
    return [ModelInfo(name="z-image-turbo", family="z-image", engine="mflux-image",
                      capabilities=["text-to-image"], repo_id="Tongyi-MAI/Z-Image-Turbo")]


def test_list_marks_downloaded_and_default():
    hub = _FakeHub(cached={"Tongyi-MAI/Z-Image-Turbo": 2_000_000_000})
    mgr = ModelManager(models_provider=_models, default_model="z-image-turbo", hub=hub)
    rows = mgr.list()
    row = rows[0]
    assert row["name"] == "z-image-turbo"
    assert row["downloaded"] is True
    assert row["is_default"] is True
    assert round(row["size_gb"], 1) == 2.0


def test_list_marks_not_downloaded():
    hub = _FakeHub(cached={})
    mgr = ModelManager(models_provider=_models, default_model="z-image-turbo", hub=hub)
    assert mgr.list()[0]["downloaded"] is False
    assert mgr.list()[0]["size_gb"] == 0


def test_download_runs_in_background_and_completes():
    hub = _FakeHub()
    mgr = ModelManager(models_provider=_models, default_model="z-image-turbo", hub=hub)
    job_id = mgr.start_download("z-image-turbo")
    for _ in range(100):
        st = mgr.download_status(job_id)
        if st["status"] in ("done", "error"):
            break
        time.sleep(0.02)
    assert mgr.download_status(job_id)["status"] == "done"
    assert "Tongyi-MAI/Z-Image-Turbo" in hub.downloaded


def test_download_unknown_model_raises():
    mgr = ModelManager(models_provider=_models, default_model="z-image-turbo", hub=_FakeHub())
    import pytest
    with pytest.raises(KeyError):
        mgr.start_download("ghost")


def test_set_default_calls_callback():
    saved = []
    mgr = ModelManager(models_provider=_models, default_model="z-image-turbo",
                       hub=_FakeHub(), on_set_default=saved.append)
    mgr.set_default("z-image-turbo")
    assert saved == ["z-image-turbo"]
    import pytest
    with pytest.raises(KeyError):
        mgr.set_default("ghost")


def test_parse_repo_id_from_url_and_plain():
    from mflux_server.models.manager import parse_repo_id
    assert parse_repo_id("https://huggingface.co/org/model") == "org/model"
    assert parse_repo_id("https://huggingface.co/org/model/tree/main") == "org/model"
    assert parse_repo_id("  org/model/  ") == "org/model"
    assert parse_repo_id("huggingface.co/a/b") == "a/b"


def test_start_download_repo_downloads_arbitrary():
    hub = _FakeHub()
    mgr = ModelManager(models_provider=_models, default_model="z-image-turbo", hub=hub)
    job_id = mgr.start_download_repo("some/other-model")
    for _ in range(100):
        if mgr.download_status(job_id)["status"] in ("done", "error"):
            break
        time.sleep(0.02)
    assert mgr.download_status(job_id)["status"] == "done"
    assert "some/other-model" in hub.downloaded


def test_start_download_repo_rejects_empty():
    mgr = ModelManager(models_provider=_models, default_model="z-image-turbo", hub=_FakeHub())
    import pytest
    with pytest.raises(ValueError):
        mgr.start_download_repo("   ")


def test_list_cached_lists_all_repos():
    hub = _FakeHub(cached={"a/one": 1_000_000_000, "b/two": 2_000_000_000})
    mgr = ModelManager(models_provider=_models, default_model="z-image-turbo", hub=hub)
    rows = mgr.list_cached()
    ids = [r["repo_id"] for r in rows]
    assert ids == ["a/one", "b/two"]
    assert round(rows[1]["size_gb"], 1) == 2.0


def test_delete_repo_executes_when_present():
    hub = _FakeHub(cached={"a/one": 1_000_000_000})
    mgr = ModelManager(models_provider=_models, default_model="z-image-turbo", hub=hub)
    assert mgr.delete_repo("a/one") is True
    assert hub.deleted          # delete_revisions(...).execute() ran
    assert mgr.delete_repo("missing/repo") is False
