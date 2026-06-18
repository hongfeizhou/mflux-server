import os
from mflux_server.engines import mflux_image
from mflux_server.engines.mflux_image import MfluxImageEngine
from mflux_server.engines.base import GenerationRequest


def test_import_does_not_require_mflux():
    # 仅构造引擎、读模型表，不应触发 mflux 导入
    engine = MfluxImageEngine()
    names = [m.name for m in engine.models()]
    assert "z-image-turbo" in names


def test_models_are_text_to_image():
    engine = MfluxImageEngine()
    for info in engine.models():
        assert "text-to-image" in info.capabilities
        assert info.engine == "mflux-image"


class _FakeModel:
    def __init__(self):
        self.calls = []

    def generate_image(self, **kwargs):
        self.calls.append(kwargs)

        class _Img:
            def save(self, path):
                with open(path, "wb") as fh:
                    fh.write(b"\x89PNG-fake")
        return _Img()


def _patch_fake_model(monkeypatch):
    fake = _FakeModel()
    spec = mflux_image._SPECS["z-image-turbo"]
    monkeypatch.setattr(spec, "loader", lambda quantize: fake)
    return fake


def test_text_to_image_passes_core_params(monkeypatch):
    fake = _patch_fake_model(monkeypatch)
    engine = mflux_image.MfluxImageEngine()
    engine.generate(GenerationRequest(model="z-image-turbo", prompt="hi",
                                      width=512, height=384, seed=5, steps=7,
                                      guidance=3.5, negative_prompt="ugly"))
    call = fake.calls[-1]
    assert call["prompt"] == "hi"
    assert call["width"] == 512 and call["height"] == 384
    assert call["seed"] == 5 and call["num_inference_steps"] == 7
    assert call["guidance"] == 3.5
    assert call["negative_prompt"] == "ugly"
    assert call.get("image_path") is None


def test_img2img_writes_init_image_and_passes_path(monkeypatch):
    fake = _patch_fake_model(monkeypatch)
    engine = mflux_image.MfluxImageEngine()
    engine.generate(GenerationRequest(model="z-image-turbo", prompt="hi",
                                      init_image=b"\x89PNG-source", image_strength=0.6))
    call = fake.calls[-1]
    assert call["image_strength"] == 0.6
    assert call["image_path"] is not None
    assert not os.path.exists(call["image_path"])


def test_model_has_repo_id():
    engine = mflux_image.MfluxImageEngine()
    infos = {m.name: m for m in engine.models()}
    assert infos["z-image-turbo"].repo_id == "Tongyi-MAI/Z-Image-Turbo"
