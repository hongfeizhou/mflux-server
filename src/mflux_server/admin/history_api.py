from fastapi import APIRouter, Depends, HTTPException, Request

from mflux_server.admin.auth import require_admin
from mflux_server.engines.base import GenerationRequest

router = APIRouter(prefix="/admin/api", dependencies=[Depends(require_admin)])


@router.get("/history")
def list_history(request: Request):
    items = []
    for e in request.app.state.history.list():
        items.append({
            "id": e.id, "prompt": e.prompt, "model": e.model,
            "params": e.params, "created_at": e.created_at,
            "url": f"/files/{e.id}.png",
        })
    return {"items": items}


@router.delete("/history/{entry_id}")
def delete_history(entry_id: str, request: Request):
    return {"deleted": request.app.state.history.delete(entry_id)}


@router.post("/history/{entry_id}/rerun")
def rerun_history(entry_id: str, request: Request):
    state = request.app.state
    entry = state.history.get(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="History entry not found")
    p = entry.params or {}
    size = p.get("size", "1024x1024")
    try:
        w, h = (int(x) for x in size.lower().split("x"))
    except (ValueError, AttributeError):
        w, h = 1024, 1024
    gen_req = GenerationRequest(
        model=entry.model, prompt=entry.prompt, width=w, height=h,
        steps=p.get("steps"), guidance=p.get("guidance"), seed=p.get("seed"),
    )
    job = state.queue.submit(gen_req)
    state.queue.wait(job, timeout=600)
    if job.status != "done":
        raise HTTPException(status_code=500, detail=job.error or "Generation failed")
    new_entry = None
    for image_bytes in job.result:
        new_entry = state.history.save(image_bytes, prompt=entry.prompt,
                                       model=entry.model, params={"size": size})
    return {"id": new_entry.id if new_entry else None}
