import pytest
from fastapi.testclient import TestClient

from mflux_server.app import create_app
from mflux_server.storage.config import ConfigStore
from mflux_server.storage.history import HistoryStore
from mflux_server.engines.registry import EngineRegistry
from mflux_server.queue import JobQueue
from tests.fakes import FakeEngine


@pytest.fixture
def ctx(tmp_path):
    config = ConfigStore(base_dir=tmp_path).load()
    registry = EngineRegistry()
    registry.register(FakeEngine(model_name="fake-model"))
    job_queue = JobQueue(registry)
    history = HistoryStore(output_dir=tmp_path / "outputs")
    app = create_app(config=config, registry=registry, job_queue=job_queue,
                     history=history, model_manager=None)
    return app, config


def test_login_page_renders(ctx):
    app, _ = ctx
    with TestClient(app) as c:
        r = c.get("/admin/login")
        assert r.status_code == 200
        assert "password" in r.text.lower()


def test_protected_page_redirects_to_login_when_anonymous(ctx):
    app, _ = ctx
    with TestClient(app) as c:
        r = c.get("/admin", follow_redirects=False)
        assert r.status_code in (302, 307)
        assert "/admin/login" in r.headers["location"]


def test_login_wrong_password_rejected(ctx):
    app, _ = ctx
    with TestClient(app) as c:
        r = c.post("/admin/login", data={"password": "wrong"}, follow_redirects=False)
        assert r.status_code in (401, 200)
        assert c.get("/admin", follow_redirects=False).status_code in (302, 307)


def test_login_correct_password_grants_session(ctx):
    app, config = ctx
    with TestClient(app) as c:
        r = c.post("/admin/login", data={"password": config.admin_password},
                   follow_redirects=False)
        assert r.status_code in (302, 307)
        assert c.get("/admin").status_code == 200


def test_logout_clears_session(ctx):
    app, config = ctx
    with TestClient(app) as c:
        c.post("/admin/login", data={"password": config.admin_password})
        c.get("/admin/logout", follow_redirects=False)
        assert c.get("/admin", follow_redirects=False).status_code in (302, 307)
