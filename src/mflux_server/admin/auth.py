import secrets
from fastapi import HTTPException, Request


def is_authed(request: Request) -> bool:
    if request.session.get("authed"):
        return True
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        expected = request.app.state.config.api_key
        if secrets.compare_digest(auth[len("Bearer "):], expected):
            return True
    return False


def require_admin(request: Request) -> None:
    if not is_authed(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
