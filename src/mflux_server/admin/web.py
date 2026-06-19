import secrets as _secrets
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from mflux_server.admin.auth import is_authed, require_admin

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
router = APIRouter()


def _guard(request: Request):
    if not is_authed(request):
        return RedirectResponse(url="/admin/login", status_code=302)
    return None


@router.get("/admin/login", response_class=HTMLResponse)
def login_page(request: Request):
    return TEMPLATES.TemplateResponse(request, "login.html", {"error": None})


@router.post("/admin/login")
def login_submit(request: Request, password: str = Form(...)):
    expected = request.app.state.config.admin_password
    if _secrets.compare_digest(password, expected):
        request.session["authed"] = True
        return RedirectResponse(url="/admin", status_code=302)
    return TEMPLATES.TemplateResponse(
        request, "login.html", {"error": "密码错误"}, status_code=401)


@router.get("/admin/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/admin/login", status_code=302)


@router.get("/admin", response_class=HTMLResponse)
def dashboard(request: Request):
    redirect = _guard(request)
    if redirect:
        return redirect
    models = request.app.state.models.list() if request.app.state.models else []
    return TEMPLATES.TemplateResponse(request, "dashboard.html", {"models": models})


@router.get("/admin/models", response_class=HTMLResponse)
def models_page(request: Request):
    redirect = _guard(request)
    if redirect:
        return redirect
    models = request.app.state.models.list() if request.app.state.models else []
    return TEMPLATES.TemplateResponse(request, "models.html", {"models": models})


@router.get("/admin/gallery", response_class=HTMLResponse)
def gallery_page(request: Request):
    redirect = _guard(request)
    if redirect:
        return redirect
    entries = request.app.state.history.list()
    return TEMPLATES.TemplateResponse(request, "gallery.html", {"entries": entries})


@router.get("/admin/api/status", response_class=HTMLResponse,
            dependencies=[Depends(require_admin)])
def status_fragment(request: Request):
    state = request.app.state
    jobs = state.queue.list()
    running = [j for j in jobs if j.status == "running"]
    queued = [j for j in jobs if j.status == "queued"]
    return TEMPLATES.TemplateResponse(request, "_status.html", {
        "running": running, "queued": queued,
        "done": len([j for j in jobs if j.status == "done"]),
        "total_history": len(state.history.list()),
    })
