import argparse
import os
from pathlib import Path

from mflux_server.app import create_app
from mflux_server.engines.mflux_image import MfluxImageEngine
from mflux_server.engines.registry import EngineRegistry
from mflux_server.logging_setup import setup_logging
from mflux_server.models.manager import ModelManager
from mflux_server.queue import JobQueue
from mflux_server.storage.config import DEFAULT_BASE, ConfigStore
from mflux_server.storage.history import HistoryStore


def build_app_from_config():
    base = Path(os.environ.get("MFLUX_SERVER_HOME", str(DEFAULT_BASE)))
    store = ConfigStore(base_dir=base)
    config = store.load()
    log_file = str(base / "logs" / "mflux-server.log")
    registry = EngineRegistry()
    registry.register(MfluxImageEngine(models_dir=config.models_dir))
    job_queue = JobQueue(registry)
    history = HistoryStore(output_dir=config.output_dir)

    def _save_default(name):
        config.default_model = name
        store.save(config)

    manager = ModelManager(
        models_provider=registry.models,
        default_model=config.default_model,
        models_dir=config.models_dir,
        on_set_default=_save_default,
    )

    def _save_config():
        store.save(config)

    return create_app(config=config, registry=registry, job_queue=job_queue,
                      history=history, model_manager=manager,
                      on_config_change=_save_config, log_file=log_file)


def main():
    parser = argparse.ArgumentParser(prog="mfserve")
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start", help="Start the server")
    start.add_argument("--host", default=None)
    start.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    if args.command == "start":
        import uvicorn
        base = Path(os.environ.get("MFLUX_SERVER_HOME", str(DEFAULT_BASE)))
        log_path = setup_logging(base)
        app = build_app_from_config()
        host = args.host or app.state.config.host
        port = args.port or app.state.config.port
        print(f"mflux-server on http://{host}:{port}")
        print(f"API key: {app.state.config.api_key}")
        print(f"Admin password: {app.state.config.admin_password}")
        print(f"Logs: {log_path}")
        uvicorn.run(app, host=host, port=port)
