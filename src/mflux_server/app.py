from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from mflux_server.api import files, openai


def create_app(config, registry, job_queue, history) -> FastAPI:
    app = FastAPI(title="mflux-server")
    app.state.config = config
    app.state.registry = registry
    app.state.queue = job_queue
    app.state.history = history

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

    app.include_router(openai.router)
    app.include_router(files.router)
    return app
