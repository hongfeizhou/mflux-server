import pytest
from fastapi.testclient import TestClient

from mflux_server.app import create_app
from mflux_server.storage.config import ConfigStore
from mflux_server.storage.history import HistoryStore
from mflux_server.engines.registry import EngineRegistry
from mflux_server.queue import JobQueue
from tests.fakes import FakeEngine, ONE_PX_PNG


class _StubManager:
    def list(self):
        return [{"name": "z-image-turbo", "downloaded": True, "is_default": True,
                 "size_gb": 32.8, "repo_id": "Tongyi-MAI/Z-Image-Turbo",
                 "family": "z-image", "capabilities": ["text-to-image"]}]


@pytest.fixture
def client(tmp_path):
    config = ConfigStore(base_dir=tmp_path).load()
    registry = EngineRegistry()
    registry.register(FakeEngine(model_name="z-image-turbo"))
    job_queue = JobQueue(registry)
    history = HistoryStore(output_dir=tmp_path / "outputs")
    app = create_app(config=config, registry=registry, job_queue=job_queue,
                     history=history, model_manager=_StubManager())
    with TestClient(app) as c:
        c.post("/admin/login", data={"password": config.admin_password})
        yield c


def test_dashboard_renders(client):
    r = client.get("/admin")
    assert r.status_code == 200
    assert "仪表盘" in r.text


def test_status_fragment_shows_counts(client):
    client.app.state.history.save(ONE_PX_PNG, prompt="x", model="z-image-turbo", params={})
    r = client.get("/admin/api/status")
    assert r.status_code == 200
    assert "队列" in r.text or "历史" in r.text


def test_status_requires_auth(client):
    fresh = TestClient(client.app)
    assert fresh.get("/admin/api/status").status_code == 401


def test_models_page_lists_models(client):
    r = client.get("/admin/models")
    assert r.status_code == 200
    assert "z-image-turbo" in r.text


def test_models_page_redirects_anonymous(client):
    fresh = TestClient(client.app)
    assert fresh.get("/admin/models", follow_redirects=False).status_code in (302, 307)


def test_gallery_shows_history(client):
    client.app.state.history.save(ONE_PX_PNG, prompt="a unicorn",
                                  model="z-image-turbo", params={"size": "256x256"})
    r = client.get("/admin/gallery")
    assert r.status_code == 200
    assert "a unicorn" in r.text
    assert "/files/" in r.text


def test_gallery_empty_renders(client):
    r = client.get("/admin/gallery")
    assert r.status_code == 200
