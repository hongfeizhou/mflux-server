from mflux_server.engines.mflux_image import MfluxImageEngine


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
