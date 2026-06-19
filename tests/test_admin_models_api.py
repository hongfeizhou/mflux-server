import pytest
from fastapi.testclient import TestClient

from mflux_server.app import create_app
from mflux_server.storage.config import ConfigStore
from mflux_server.storage.history import HistoryStore
from mflux_server.engines.registry import EngineRegistry
from mflux_server.queue import JobQueue
from tests.fakes import FakeEngine


class _StubManager:
    def __init__(self):
        self.default = None
        self.downloads = {}

    def list(self):
        return [{"name": "fake-model", "downloaded": True, "is_default": True,
                 "size_gb": 1.5, "repo_id": "org/fake", "family": "fake",
                 "capabilities": ["text-to-image"]}]

    def start_download(self, name):
        if name == "ghost":
            raise KeyError(name)
        self.downloads["job1"] = {"status": "running", "repo_id": "org/fake", "error": None}
        return "job1"

    def download_status(self, job_id):
        return {"status": "done", "repo_id": "org/fake", "error": None}

    def delete(self, name):
        return True

    def set_default(self, name):
        if name == "ghost":
            raise KeyError(name)
        self.default = name

    def list_cached(self):
        return [{"repo_id": "org/fake", "size_gb": 1.5}]

    def start_download_repo(self, repo_id):
        self.downloads["repojob"] = {"status": "running", "repo_id": repo_id, "error": None}
        self.last_repo = repo_id
        return "repojob"

    def delete_repo(self, repo_id):
        self.deleted_repo = repo_id
        return True


@pytest.fixture
def client(tmp_path):
    config = ConfigStore(base_dir=tmp_path).load()
    registry = EngineRegistry()
    registry.register(FakeEngine(model_name="fake-model"))
    job_queue = JobQueue(registry)
    history = HistoryStore(output_dir=tmp_path / "outputs")
    manager = _StubManager()
    app = create_app(config=config, registry=registry, job_queue=job_queue,
                     history=history, model_manager=manager)
    with TestClient(app) as c:
        c.api_key = config.api_key
        c.manager = manager
        yield c


def _auth(c):
    return {"Authorization": f"Bearer {c.api_key}"}


def test_list_models_requires_auth(client):
    assert client.get("/admin/api/models").status_code == 401


def test_list_models(client):
    r = client.get("/admin/api/models", headers=_auth(client))
    assert r.status_code == 200
    assert r.json()["models"][0]["name"] == "fake-model"


def test_start_download_and_status(client):
    r = client.post("/admin/api/models/fake-model/download", headers=_auth(client))
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    s = client.get(f"/admin/api/models/downloads/{job_id}", headers=_auth(client))
    assert s.json()["status"] == "done"


def test_download_unknown_model_404(client):
    r = client.post("/admin/api/models/ghost/download", headers=_auth(client))
    assert r.status_code == 404


def test_delete_model(client):
    r = client.request("DELETE", "/admin/api/models/fake-model", headers=_auth(client))
    assert r.status_code == 200
    assert r.json()["deleted"] is True


def test_set_default(client):
    r = client.post("/admin/api/models/fake-model/default", headers=_auth(client))
    assert r.status_code == 200
    assert client.manager.default == "fake-model"


def test_set_default_unknown_404(client):
    r = client.post("/admin/api/models/ghost/default", headers=_auth(client))
    assert r.status_code == 404


def test_list_models_via_session_cookie(client):
    assert client.get("/admin/api/models").status_code == 401
    pw = client.app.state.config.admin_password
    client.post("/admin/login", data={"password": pw})
    r = client.get("/admin/api/models")
    assert r.status_code == 200


def test_list_repos(client):
    r = client.get("/admin/api/repos", headers=_auth(client))
    assert r.status_code == 200
    assert r.json()["repos"][0]["repo_id"] == "org/fake"


def test_download_repo_parses_url(client):
    r = client.post("/admin/api/repos/download",
                    headers=_auth(client),
                    data={"repo": "https://huggingface.co/org/fake/tree/main"})
    assert r.status_code == 200
    assert r.json()["repo_id"] == "org/fake"
    assert client.manager.last_repo == "org/fake"


def test_download_repo_requires_auth(client):
    r = client.post("/admin/api/repos/download", data={"repo": "org/fake"})
    assert r.status_code == 401


def test_delete_repo_with_slash_path(client):
    r = client.request("DELETE", "/admin/api/repos/org/fake", headers=_auth(client))
    assert r.status_code == 200
    assert r.json()["deleted"] is True
    assert client.manager.deleted_repo == "org/fake"
