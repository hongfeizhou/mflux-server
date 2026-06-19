import os
from mflux_server.engines import mflux_image
from mflux_server.engines.mflux_image import MfluxImageEngine
from mflux_server.engines.base import GenerationRequest


def test_import_does_not_require_mflux():
    # 仅构造引擎、读模型表，不应触发 mflux 导入
    engine = MfluxImageEngine()
    names = [m.name for m in engine.models()]
    assert "z-image-turbo" in names


def test_models_have_engine_and_capabilities():
    engine = MfluxImageEngine()
    infos = {m.name: m for m in engine.models()}
    for info in infos.values():
        assert info.engine == "mflux-image"
        assert info.capabilities
    # z-image-turbo / flux2 do both; qwen-image-edit is edit-only
    assert "text-to-image" in infos["z-image-turbo"].capabilities
    assert "text-to-image" in infos["flux2-klein-4b"].capabilities
    assert infos["qwen-image-edit"].capabilities == ["image-to-image"]


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
    monkeypatch.setattr(spec, "loader", lambda quantize, model_path=None: fake)
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
    assert infos["flux2-klein-4b"].repo_id == "black-forest-labs/FLUX.2-klein-4B"


class _NoNegModel:
    """generate_image 没有 negative_prompt（像 Flux2Klein）。"""
    def __init__(self):
        self.calls = []

    def generate_image(self, seed, prompt, num_inference_steps=4,
                       width=1024, height=1024, guidance=1.0):
        self.calls.append(dict(seed=seed, prompt=prompt, num_inference_steps=num_inference_steps,
                               width=width, height=height, guidance=guidance))
        class _Img:
            def save(self, path):
                with open(path, "wb") as fh:
                    fh.write(b"x")
        return _Img()


class _EditModel:
    """编辑模型：generate_image 用 image_paths(列表)，无 image_strength（像 QwenImageEdit）。"""
    def __init__(self):
        self.calls = []

    def generate_image(self, seed, prompt, image_paths, num_inference_steps=4):
        self.calls.append(dict(seed=seed, prompt=prompt, image_paths=image_paths,
                               num_inference_steps=num_inference_steps))
        class _Img:
            def save(self, path):
                with open(path, "wb") as fh:
                    fh.write(b"x")
        return _Img()


def test_generate_drops_kwargs_model_does_not_accept(monkeypatch):
    fake = _NoNegModel()
    monkeypatch.setattr(mflux_image._SPECS["z-image-turbo"], "loader",
                        lambda quantize, model_path=None: fake)
    mflux_image.MfluxImageEngine().generate(
        GenerationRequest(model="z-image-turbo", prompt="hi",
                          negative_prompt="ugly", guidance=2.0, image_strength=0.5))
    call = fake.calls[-1]
    assert "negative_prompt" not in call      # 模型没有该参数 -> 丢弃
    assert "image_strength" not in call        # 同上
    assert call["guidance"] == 2.0             # 模型有 -> 传入


def test_generate_edit_model_uses_image_paths(monkeypatch):
    fake = _EditModel()
    monkeypatch.setattr(mflux_image._SPECS["qwen-image-edit"], "loader",
                        lambda quantize, model_path=None: fake)
    mflux_image.MfluxImageEngine().generate(
        GenerationRequest(model="qwen-image-edit", prompt="edit", init_image=b"PNG"))
    call = fake.calls[-1]
    assert isinstance(call["image_paths"], list) and call["image_paths"][0]
