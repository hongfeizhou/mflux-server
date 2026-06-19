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
    registry.register(FakeEngine(model_name="z-image-turbo"))
    job_queue = JobQueue(registry)
    history = HistoryStore(output_dir=tmp_path / "outputs")
    app = create_app(config=config, registry=registry, job_queue=job_queue,
                     history=history, model_manager=None)
    with TestClient(app) as c:
        c.post("/admin/login", data={"password": config.admin_password})
        yield c


def test_generate_page_renders(client):
    r = client.get("/admin/generate")
    assert r.status_code == 200
    assert 'name="prompt"' in r.text


def test_generate_page_redirects_anonymous(client):
    fresh = TestClient(client.app)
    assert fresh.get("/admin/generate", follow_redirects=False).status_code in (302, 307)


def test_generate_text_to_image(client):
    r = client.post("/admin/api/generate",
                    data={"prompt": "a blue car", "model": "z-image-turbo", "size": "256x256"})
    assert r.status_code == 200
    assert "/files/" in r.text
    req = client.app.state.registry.engine_for("z-image-turbo").calls[-1]
    assert req.prompt == "a blue car"
    assert req.init_image is None
    assert len(client.app.state.history.list()) == 1


def test_generate_img2img(client):
    files = {"image": ("src.png", b"\x89PNG-source", "image/png")}
    data = {"prompt": "watercolor", "model": "z-image-turbo", "size": "256x256", "strength": "0.6"}
    r = client.post("/admin/api/generate", files=files, data=data)
    assert r.status_code == 200
    req = client.app.state.registry.engine_for("z-image-turbo").calls[-1]
    assert req.init_image == b"\x89PNG-source"
    assert req.image_strength == 0.6


def test_generate_requires_auth(client):
    fresh = TestClient(client.app)
    assert fresh.post("/admin/api/generate", data={"prompt": "x"}).status_code == 401
