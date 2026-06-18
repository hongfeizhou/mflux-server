import secrets as _secrets
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from mflux_server.admin.auth import is_authed

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
    return TEMPLATES.TemplateResponse(request, "dashboard.html")
