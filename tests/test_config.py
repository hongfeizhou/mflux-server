from pathlib import Path
from mflux_server.storage.config import ConfigStore


def test_load_creates_config_with_generated_api_key(tmp_path: Path):
    store = ConfigStore(base_dir=tmp_path)
    cfg = store.load()
    assert cfg.api_key.startswith("sk-")
    assert (tmp_path / "config.json").exists()
    assert cfg.output_dir == str(tmp_path / "outputs")


def test_load_is_stable_across_calls(tmp_path: Path):
    store = ConfigStore(base_dir=tmp_path)
    first = store.load()
    second = ConfigStore(base_dir=tmp_path).load()
    assert first.api_key == second.api_key
    assert first.admin_password == second.admin_password


def test_save_then_load_roundtrip(tmp_path: Path):
    store = ConfigStore(base_dir=tmp_path)
    cfg = store.load()
    cfg.port = 9123
    store.save(cfg)
    assert ConfigStore(base_dir=tmp_path).load().port == 9123
