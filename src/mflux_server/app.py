from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from mflux_server.admin import history_api, web as admin_web
from mflux_server.api import admin_models, files, openai


def create_app(config, registry, job_queue, history, model_manager=None,
               on_config_change=None, log_file=None) -> FastAPI:
    app = FastAPI(title="mflux-server")
    app.state.config = config
    app.state.registry = registry
    app.state.queue = job_queue
    app.state.history = history
    app.state.models = model_manager
    app.state.on_config_change = on_config_change
    app.state.log_file = log_file

    @app.on_event("startup")
    def _start_worker():
        job_queue.start()

    @app.exception_handler(HTTPException)
    def _openai_error(request, exc: HTTPException):
        code_map = {400: "invalid_request_error", 401: "authentication_error",
                    404: "invalid_request_error", 500: "server_error"}
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {
                "message": exc.detail,
                "type": code_map.get(exc.status_code, "server_error"),
                "code": exc.status_code,
            }},
        )

    app.add_middleware(SessionMiddleware, secret_key=config.api_key)
    _static = Path(__file__).parent / "admin" / "static"
    app.mount("/admin/static", StaticFiles(directory=str(_static)), name="admin-static")
    app.include_router(admin_web.router)
    app.include_router(openai.router)
    app.include_router(files.router)
    app.include_router(admin_models.router)
    app.include_router(history_api.router)
    return app
