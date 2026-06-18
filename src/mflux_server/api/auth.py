from fastapi import Header, HTTPException, Request
from typing import Optional


def require_api_key(request: Request, authorization: Optional[str] = Header(None)) -> None:
    expected = request.app.state.config.api_key
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer API key")
    if authorization[len("Bearer "):] != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")
