from unittest.mock import MagicMock

from mflux_server.cli import build_app_from_config


def test_build_app_from_config_wires_everything(tmp_path, monkeypatch):
    monkeypatch.setenv("MFLUX_SERVER_HOME", str(tmp_path))
    stub_manager = MagicMock()
    monkeypatch.setattr("mflux_server.cli.ModelManager",
                        lambda **_kwargs: stub_manager)
    app = build_app_from_config()
    assert app.state.config.api_key.startswith("sk-")
    # mflux 引擎已注册
    assert app.state.registry.find_model("z-image-turbo") is not None
