import pytest
from fastapi.testclient import TestClient

from mflux_server.app import create_app
from mflux_server.storage.config import ConfigStore
from mflux_server.storage.history import HistoryStore
from mflux_server.engines.registry import EngineRegistry
from mflux_server.queue import JobQueue
from tests.fakes import FakeEngine


class _Mgr:
    def __init__(self):
        self._status = "running"
        self.last = None

    def list(self):
        return []

    def list_cached(self):
        return []

    def start_download_repo(self, repo_id):
        self.last = repo_id
        return "job-1"

    def start_download(self, name):
        if name == "ghost":
            raise KeyError(name)
        return "job-2"

    def download_status(self, job_id):
        return {"status": self._status, "repo_id": "org/x",
                "error": "boom" if self._status == "error" else None}


@pytest.fixture
def client(tmp_path):
    config = ConfigStore(base_dir=tmp_path).load()
    registry = EngineRegistry()
    registry.register(FakeEngine(model_name="fake-model"))
    job_queue = JobQueue(registry)
    history = HistoryStore(output_dir=tmp_path / "outputs")
    mgr = _Mgr()
    app = create_app(config=config, registry=registry, job_queue=job_queue,
                     history=history, model_manager=mgr)
    with TestClient(app) as c:
        c.post("/admin/login", data={"password": config.admin_password})
        c.mgr = mgr
        yield c


def test_repo_download_ui_starts_and_polls(client):
    r = client.post("/admin/repos/download",
                    data={"repo": "https://huggingface.co/org/x/tree/main"})
    assert r.status_code == 200
    assert client.mgr.last == "org/x"
    assert "/admin/repos/download/job-1" in r.text
    assert "every 2s" in r.text


def test_catalog_download_ui(client):
    r = client.post("/admin/models/fake-model/download-ui")
    assert r.status_code == 200
    assert "/admin/repos/download/job-2" in r.text


def test_catalog_download_ui_unknown_404(client):
    assert client.post("/admin/models/ghost/download-ui").status_code == 404


def test_download_status_done_stops_polling(client):
    client.mgr._status = "done"
    r = client.get("/admin/repos/download/job-1")
    assert r.status_code == 200
    assert "every 2s" not in r.text


def test_download_ui_requires_auth(client):
    fresh = TestClient(client.app)
    assert fresh.post("/admin/repos/download", data={"repo": "org/x"}).status_code == 401
