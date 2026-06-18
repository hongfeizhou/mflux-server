from fastapi import APIRouter, Depends, HTTPException, Request

from mflux_server.api.auth import require_api_key

router = APIRouter(prefix="/admin/api", dependencies=[Depends(require_api_key)])


@router.get("/models")
def list_models(request: Request):
    return {"models": request.app.state.models.list()}


@router.post("/models/{name}/download")
def download_model(name: str, request: Request):
    try:
        job_id = request.app.state.models.start_download(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Model not found: {name}")
    return {"job_id": job_id}


@router.get("/models/downloads/{job_id}")
def download_status(job_id: str, request: Request):
    try:
        return request.app.state.models.download_status(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Download job not found")


@router.delete("/models/{name}")
def delete_model(name: str, request: Request):
    try:
        deleted = request.app.state.models.delete(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Model not found: {name}")
    return {"deleted": deleted}


@router.post("/models/{name}/default")
def set_default(name: str, request: Request):
    try:
        request.app.state.models.set_default(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Model not found: {name}")
    return {"default_model": name}
