import json
import secrets
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_BASE = Path.home() / ".mflux-server"


@dataclass
class Config:
    api_key: str
    admin_password: str
    output_dir: str
    host: str = "127.0.0.1"
    port: int = 8000
    default_model: str = "z-image-turbo"
    default_steps: int = 9
    models_dir: str = ""


class ConfigStore:
    def __init__(self, base_dir: Path = DEFAULT_BASE):
        self.base_dir = Path(base_dir)
        self.path = self.base_dir / "config.json"

    def load(self) -> Config:
        if self.path.exists():
            cfg = Config(**json.loads(self.path.read_text(encoding="utf-8")))
            if not cfg.models_dir:
                cfg.models_dir = str(self.base_dir / "models")
                self.save(cfg)
            return cfg
        cfg = Config(
            api_key="sk-" + secrets.token_hex(24),
            admin_password=secrets.token_hex(8),
            output_dir=str(self.base_dir / "outputs"),
            models_dir=str(self.base_dir / "models"),
        )
        self.save(cfg)
        return cfg

    def save(self, cfg: Config) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")
