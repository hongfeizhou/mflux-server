import base64
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from mflux_server.api.auth import require_api_key
from mflux_server.engines.base import GenerationRequest

router = APIRouter()


class GenerationsBody(BaseModel):
    prompt: str
    model: Optional[str] = None
    n: int = 1
    size: str = "1024x1024"
    response_format: str = "b64_json"
    steps: Optional[int] = None
    guidance: Optional[float] = None
    seed: Optional[int] = None
    lora: list = []
    quantize: Optional[int] = None


def _parse_size(size: str):
    try:
        w, h = size.lower().split("x")
        return int(w), int(h)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail=f"Invalid size: {size!r}")


@router.post("/v1/images/generations", dependencies=[Depends(require_api_key)])
def generations(body: GenerationsBody, request: Request):
    state = request.app.state
    model_name = body.model or state.config.default_model
    if state.registry.find_model(model_name) is None:
        raise HTTPException(status_code=404, detail=f"Model not found: {model_name}")

    width, height = _parse_size(body.size)
    gen_req = GenerationRequest(
        model=model_name, prompt=body.prompt, n=body.n,
        width=width, height=height, steps=body.steps,
        guidance=body.guidance, seed=body.seed,
        lora=body.lora, quantize=body.quantize,
    )
    job = state.queue.submit(gen_req)
    state.queue.wait(job, timeout=600)
    if job.status != "done":
        raise HTTPException(status_code=500, detail=job.error or "Generation timed out")

    params = {"steps": body.steps, "guidance": body.guidance,
              "seed": body.seed, "size": body.size}
    data = []
    for image_bytes in job.result:
        entry = state.history.save(image_bytes, prompt=body.prompt,
                                   model=model_name, params=params)
        if body.response_format == "url":
            base = str(request.base_url).rstrip("/")
            data.append({"url": f"{base}/files/{entry.id}.png"})
        else:
            data.append({"b64_json": base64.b64encode(image_bytes).decode()})
    return {"created": int(time.time()), "data": data}


@router.get("/v1/models", dependencies=[Depends(require_api_key)])
def list_models(request: Request):
    models = request.app.state.registry.models()
    return {
        "object": "list",
        "data": [
            {"id": m.name, "object": "model", "owned_by": m.engine}
            for m in models
        ],
    }
