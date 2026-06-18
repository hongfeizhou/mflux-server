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
    app = create_app(config=config, registry=registry,
                     job_queue=job_queue, history=history)
    with TestClient(app) as c:
        c.api_key = config.api_key
        yield c


def _auth(client):
    return {"Authorization": f"Bearer {client.api_key}"}


def test_generations_requires_api_key(client):
    r = client.post("/v1/images/generations", json={"prompt": "hi", "model": "fake-model"})
    assert r.status_code == 401
    assert r.json()["error"]["type"]


def test_generations_returns_b64(client):
    r = client.post("/v1/images/generations",
                    headers=_auth(client),
                    json={"prompt": "hi", "model": "fake-model", "n": 2})
    assert r.status_code == 200
    body = r.json()
    assert len(body["data"]) == 2
    assert base64.b64decode(body["data"][0]["b64_json"]) == ONE_PX_PNG


def test_generations_url_format_serves_file(client):
    r = client.post("/v1/images/generations",
                    headers=_auth(client),
                    json={"prompt": "hi", "model": "fake-model",
                          "response_format": "url"})
    url = r.json()["data"][0]["url"]
    path = url[url.index("/files/"):]
    img = client.get(path)
    assert img.status_code == 200
    assert img.content == ONE_PX_PNG


def test_unknown_model_returns_404_openai_error(client):
    r = client.post("/v1/images/generations",
                    headers=_auth(client),
                    json={"prompt": "hi", "model": "ghost"})
    assert r.status_code == 404
    assert r.json()["error"]["message"]


def test_size_parsing_passes_dimensions(client):
    r = client.post("/v1/images/generations",
                    headers=_auth(client),
                    json={"prompt": "hi", "model": "fake-model", "size": "512x768"})
    assert r.status_code == 200
    req = client.app.state.registry.engine_for("fake-model").calls[-1]
    assert (req.width, req.height) == (512, 768)


def test_list_models(client):
    r = client.get("/v1/models", headers=_auth(client))
    assert r.status_code == 200
    ids = [m["id"] for m in r.json()["data"]]
    assert "fake-model" in ids


def test_edits_img2img_returns_b64_and_passes_init_image(client):
    files = {"image": ("src.png", b"\x89PNG-source", "image/png")}
    data = {"prompt": "make it blue", "model": "fake-model",
            "strength": "0.55", "size": "256x256"}
    r = client.post("/v1/images/edits", headers=_auth(client), files=files, data=data)
    assert r.status_code == 200
    body = r.json()
    assert base64.b64decode(body["data"][0]["b64_json"]) == ONE_PX_PNG
    req = client.app.state.registry.engine_for("fake-model").calls[-1]
    assert req.init_image == b"\x89PNG-source"
    assert req.image_strength == 0.55
    assert (req.width, req.height) == (256, 256)


def test_edits_requires_api_key(client):
    files = {"image": ("src.png", b"\x89PNG", "image/png")}
    r = client.post("/v1/images/edits", files=files, data={"prompt": "x"})
    assert r.status_code == 401
