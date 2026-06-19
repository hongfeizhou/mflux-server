from fastapi import APIRouter, Depends, Form, HTTPException, Request

from mflux_server.admin.auth import require_admin
from mflux_server.models.manager import parse_repo_id

router = APIRouter(prefix="/admin/api", dependencies=[Depends(require_admin)])


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


@router.get("/repos")
def list_repos(request: Request):
    return {"repos": request.app.state.models.list_cached()}


@router.post("/repos/download")
def download_repo(request: Request, repo: str = Form(...)):
    repo_id = parse_repo_id(repo)
    try:
        job_id = request.app.state.models.start_download_repo(repo_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid repository id")
    return {"job_id": job_id, "repo_id": repo_id}


@router.delete("/repos/{repo_id:path}")
def delete_repo(repo_id: str, request: Request):
    return {"deleted": request.app.state.models.delete_repo(repo_id)}
