from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

router = APIRouter()


@router.get("/files/{entry_id}.png")
def get_file(entry_id: str, request: Request):
    path = request.app.state.history.image_path(entry_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(path, media_type="image/png")
