from pathlib import Path
from mflux_server.storage.history import HistoryStore

PNG = b"\x89PNG\r\n\x1a\n-fake-bytes"


def test_save_writes_png_and_metadata(tmp_path: Path):
    store = HistoryStore(output_dir=tmp_path)
    entry = store.save(PNG, prompt="a cat", model="z-image-turbo", params={"seed": 1})
    assert (tmp_path / f"{entry.id}.png").read_bytes() == PNG
    assert (tmp_path / f"{entry.id}.json").exists()
    assert entry.prompt == "a cat"
    assert entry.model == "z-image-turbo"


def test_get_returns_saved_entry(tmp_path: Path):
    store = HistoryStore(output_dir=tmp_path)
    entry = store.save(PNG, prompt="p", model="m", params={})
    loaded = store.get(entry.id)
    assert loaded is not None
    assert loaded.prompt == "p"
    assert store.get("nonexistent") is None


def test_list_sorted_newest_first(tmp_path: Path):
    store = HistoryStore(output_dir=tmp_path)
    a = store.save(PNG, prompt="a", model="m", params={}, created_at=100.0)
    b = store.save(PNG, prompt="b", model="m", params={}, created_at=200.0)
    ids = [e.id for e in store.list()]
    assert ids == [b.id, a.id]


def test_delete_removes_files(tmp_path: Path):
    store = HistoryStore(output_dir=tmp_path)
    entry = store.save(PNG, prompt="p", model="m", params={})
    assert store.delete(entry.id) is True
    assert not (tmp_path / f"{entry.id}.png").exists()
    assert store.delete(entry.id) is False
