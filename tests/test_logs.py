import pytest
from fastapi.testclient import TestClient

from mflux_server.app import create_app
from mflux_server.storage.config import ConfigStore
from mflux_server.storage.history import HistoryStore
from mflux_server.engines.registry import EngineRegistry
from mflux_server.queue import JobQueue
from tests.fakes import FakeEngine


@pytest.fixture
def client(tmp_path):
    config = ConfigStore(base_dir=tmp_path).load()
    registry = EngineRegistry()
    registry.register(FakeEngine(model_name="fake-model"))
    job_queue = JobQueue(registry)
    history = HistoryStore(output_dir=tmp_path / "outputs")
    log_file = tmp_path / "logs" / "app.log"
    log_file.parent.mkdir(parents=True)
    log_file.write_text("hello-log-line\nsecond-line\n", encoding="utf-8")
    app = create_app(config=config, registry=registry, job_queue=job_queue,
                     history=history, model_manager=None, log_file=str(log_file))
    with TestClient(app) as c:
        c.post("/admin/login", data={"password": config.admin_password})
        yield c


def test_logs_page_renders(client):
    r = client.get("/admin/logs")
    assert r.status_code == 200
    assert "/admin/api/logs" in r.text


def test_logs_tail_returns_content(client):
    r = client.get("/admin/api/logs")
    assert r.status_code == 200
    assert "hello-log-line" in r.text


def test_logs_tail_requires_auth(client):
    fresh = TestClient(client.app)
    assert fresh.get("/admin/api/logs").status_code == 401


def test_logs_page_redirects_anonymous(client):
    fresh = TestClient(client.app)
    assert fresh.get("/admin/logs", follow_redirects=False).status_code in (302, 307)
