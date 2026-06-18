import base64
import pytest
from fastapi.testclient import TestClient

from mflux_server.app import create_app
from mflux_server.storage.config import ConfigStore
from mflux_server.storage.history import HistoryStore
from mflux_server.engines.registry import EngineRegistry
from mflux_server.queue import JobQueue
from tests.fakes import FakeEngine, ONE_PX_PNG


@pytest.fixture
def client(tmp_path):
    config = ConfigStore(base_dir=tmp_path).load()
    registry = EngineRegistry()
    registry.register(FakeEngine(model_name="fake-model"))
    job_queue = JobQueue(registry)
    history = HistoryStore(output_dir=tmp_path / "outputs")
    app = create_app(config=config, registry=registry, job_queue=job_queue,
                     history=history, model_manager=None)
    with TestClient(app) as c:
        c.api_key = config.api_key
        yield c


def _auth(c):
    return {"Authorization": f"Bearer {c.api_key}"}


def _seed(client, prompt="a cat"):
    return client.app.state.history.save(ONE_PX_PNG, prompt=prompt,
                                         model="fake-model", params={"size": "256x256"})


def test_history_list(client):
    _seed(client, "a")
    _seed(client, "b")
    r = client.get("/admin/api/history", headers=_auth(client))
    assert r.status_code == 200
    assert len(r.json()["items"]) == 2


def test_history_list_requires_auth(client):
    assert client.get("/admin/api/history").status_code == 401


def test_history_delete(client):
    e = _seed(client)
    r = client.request("DELETE", f"/admin/api/history/{e.id}", headers=_auth(client))
    assert r.status_code == 200 and r.json()["deleted"] is True
    assert client.get("/admin/api/history", headers=_auth(client)).json()["items"] == []


def test_history_rerun_resubmits(client):
    e = _seed(client, "a robot")
    r = client.post(f"/admin/api/history/{e.id}/rerun", headers=_auth(client))
    assert r.status_code == 200
    req = client.app.state.registry.engine_for("fake-model").calls[-1]
    assert req.prompt == "a robot"


def test_history_rerun_unknown_404(client):
    r = client.post("/admin/api/history/nope/rerun", headers=_auth(client))
    assert r.status_code == 404
