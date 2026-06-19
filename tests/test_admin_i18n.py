import pytest
from fastapi.testclient import TestClient

from mflux_server.app import create_app
from mflux_server.storage.config import ConfigStore
from mflux_server.storage.history import HistoryStore
from mflux_server.engines.registry import EngineRegistry
from mflux_server.queue import JobQueue
from tests.fakes import FakeEngine


@pytest.fixture
def app(tmp_path):
    config = ConfigStore(base_dir=tmp_path).load()
    registry = EngineRegistry()
    registry.register(FakeEngine(model_name="fake-model"))
    job_queue = JobQueue(registry)
    history = HistoryStore(output_dir=tmp_path / "outputs")
    return create_app(config=config, registry=registry, job_queue=job_queue,
                      history=history, model_manager=None)


def test_login_default_english(app):
    with TestClient(app) as c:
        r = c.get("/admin/login")
        assert "Sign in" in r.text
        assert "登录" not in r.text


def test_login_chinese_with_cookie(app):
    with TestClient(app) as c:
        c.cookies.set("lang", "zh")
        r = c.get("/admin/login")
        assert "登录" in r.text


def test_setlang_sets_cookie_and_redirects(app):
    with TestClient(app) as c:
        r = c.get("/admin/setlang?code=zh&next=/admin/login", follow_redirects=False)
        assert r.status_code in (302, 307)
        assert r.headers["location"] == "/admin/login"
        assert c.cookies.get("lang") == "zh"


def test_setlang_rejects_unknown_code(app):
    with TestClient(app) as c:
        c.get("/admin/setlang?code=fr&next=/admin/login")
        r = c.get("/admin/login")
        assert "Sign in" in r.text
