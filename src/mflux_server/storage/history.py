import json
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional


@dataclass
class HistoryEntry:
    id: str
    prompt: str
    model: str
    params: dict
    created_at: float


class HistoryStore:
    def __init__(self, output_dir):
        self.output_dir = Path(output_dir)

    def save(self, image_bytes: bytes, prompt: str, model: str,
             params: dict, created_at: Optional[float] = None) -> HistoryEntry:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        entry = HistoryEntry(
            id=uuid.uuid4().hex,
            prompt=prompt,
            model=model,
            params=params,
            created_at=created_at if created_at is not None else time.time(),
        )
        (self.output_dir / f"{entry.id}.png").write_bytes(image_bytes)
        (self.output_dir / f"{entry.id}.json").write_text(
            json.dumps(asdict(entry), indent=2), encoding="utf-8"
        )
        return entry

    def image_path(self, entry_id: str) -> Path:
        return self.output_dir / f"{entry_id}.png"

    def get(self, entry_id: str) -> Optional[HistoryEntry]:
        meta = self.output_dir / f"{entry_id}.json"
        if not meta.exists():
            return None
        return HistoryEntry(**json.loads(meta.read_text(encoding="utf-8")))

    def list(self) -> list:
        if not self.output_dir.exists():
            return []
        entries = []
        for meta in self.output_dir.glob("*.json"):
            entries.append(HistoryEntry(**json.loads(meta.read_text(encoding="utf-8"))))
        return sorted(entries, key=lambda e: e.created_at, reverse=True)

    def delete(self, entry_id: str) -> bool:
        png = self.output_dir / f"{entry_id}.png"
        meta = self.output_dir / f"{entry_id}.json"
        if not meta.exists():
            return False
        png.unlink(missing_ok=True)
        meta.unlink(missing_ok=True)
        return True
