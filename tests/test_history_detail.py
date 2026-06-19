import pytest
from fastapi.testclient import TestClient

from mflux_server.app import create_app
from mflux_server.storage.config import ConfigStore
from mflux_server.storage.history import HistoryStore
from mflux_server.engines.registry import EngineRegistry
from mflux_server.queue import JobQueue
from mflux_server.engines.base import GenerationRequest
from tests.fakes import FakeEngine, ONE_PX_PNG


def test_job_records_duration():
    reg = EngineRegistry()
    reg.register(FakeEngine(model_name="fake-model"))
    q = JobQueue(reg)
    q.start()
    job = q.submit(GenerationRequest(model="fake-model", prompt="hi"))
    q.wait(job, timeout=5)
    assert job.status == "done"
    assert job.duration is not None and job.duration >= 0


@pytest.fixture
def client(tmp_path):
    config = ConfigStore(base_dir=tmp_path).load()
    registry = EngineRegistry()
    registry.register(FakeEngine(model_name="z-image-turbo"))
    job_queue = JobQueue(registry)
    history = HistoryStore(output_dir=tmp_path / "outputs")
    app = create_app(config=config, registry=registry, job_queue=job_queue,
                     history=history, model_manager=None)
    with TestClient(app) as c:
        c.api_key = config.api_key
        c.post("/admin/login", data={"password": config.admin_password})
        yield c


def test_generations_records_duration_in_history(client):
    r = client.post("/v1/images/generations",
                    headers={"Authorization": f"Bearer {client.api_key}"},
                    json={"model": "z-image-turbo", "prompt": "x", "size": "128x128"})
    assert r.status_code == 200
    entry = client.app.state.history.list()[0]
    assert "duration" in entry.params
    assert entry.params["duration"] is not None


def test_gallery_shows_params_and_duration(client):
    client.app.state.history.save(ONE_PX_PNG, prompt="a robot",
                                  model="z-image-turbo",
                                  params={"size": "256x256", "seed": 7, "duration": 1.23})
    r = client.get("/admin/gallery")
    assert r.status_code == 200
    assert "256x256" in r.text
    assert "7" in r.text
    assert "1.2" in r.text
