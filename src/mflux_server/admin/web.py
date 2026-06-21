import secrets as _secrets
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from mflux_server.admin.auth import is_authed, require_admin
from mflux_server.admin.i18n import i18n_context, SUPPORTED
from mflux_server.engines.base import GenerationRequest
from mflux_server.models.manager import parse_repo_id

TEMPLATES = Jinja2Templates(
    directory=str(Path(__file__).parent / "templates"),
    context_processors=[i18n_context],
)
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
        request, "login.html", {"error": True}, status_code=401)


@router.get("/admin/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/admin/login", status_code=302)


@router.get("/admin/setlang")
def setlang(request: Request, code: str = "en", next: str = "/admin"):
    if not next.startswith("/"):
        next = "/admin"
    resp = RedirectResponse(url=next, status_code=302)
    if code in SUPPORTED:
        resp.set_cookie("lang", code, max_age=31536000, httponly=False, samesite="lax")
    return resp


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
    mgr = request.app.state.models
    models = mgr.list() if mgr else []
    cached = mgr.list_cached() if mgr else []
    return TEMPLATES.TemplateResponse(request, "models.html",
                                      {"models": models, "cached": cached,
                                       "models_dir": request.app.state.config.models_dir})


@router.get("/admin/gallery", response_class=HTMLResponse)
def gallery_page(request: Request):
    redirect = _guard(request)
    if redirect:
        return redirect
    entries = request.app.state.history.list()
    return TEMPLATES.TemplateResponse(request, "gallery.html", {"entries": entries})


@router.get("/admin/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    redirect = _guard(request)
    if redirect:
        return redirect
    return TEMPLATES.TemplateResponse(request, "settings.html",
                                      {"cfg": request.app.state.config})


@router.post("/admin/api/regenerate-key", dependencies=[Depends(require_admin)])
def regenerate_key(request: Request):
    config = request.app.state.config
    config.api_key = "sk-" + _secrets.token_hex(24)
    if getattr(request.app.state, "on_config_change", None):
        request.app.state.on_config_change()
    return {"api_key": config.api_key}


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


@router.get("/admin/generate", response_class=HTMLResponse)
def generate_page(request: Request):
    redirect = _guard(request)
    if redirect:
        return redirect
    models = [m for m in request.app.state.registry.models()
              if "text-to-image" in m.capabilities]
    return TEMPLATES.TemplateResponse(request, "generate.html",
                                      {"models": models, "active": "text"})


@router.get("/admin/generate/edit", response_class=HTMLResponse)
def generate_edit_page(request: Request):
    redirect = _guard(request)
    if redirect:
        return redirect
    models = [m for m in request.app.state.registry.models()
              if "image-to-image" in m.capabilities]
    return TEMPLATES.TemplateResponse(request, "generate_edit.html",
                                      {"models": models, "active": "edit"})


def _parse_gen_size(size: str):
    try:
        w, h = size.lower().split("x")
        return int(w), int(h)
    except (ValueError, AttributeError):
        return 1024, 1024


@router.post("/admin/api/generate", response_class=HTMLResponse,
             dependencies=[Depends(require_admin)])
def generate_action(
    request: Request,
    prompt: str = Form(...),
    model: Optional[str] = Form(None),
    size: str = Form("1024x1024"),
    steps: Optional[int] = Form(None),
    seed: Optional[int] = Form(None),
    negative_prompt: Optional[str] = Form(None),
    strength: Optional[float] = Form(None),
    image: Optional[UploadFile] = File(None),
):
    state = request.app.state
    model_name = model or state.config.default_model
    if state.registry.find_model(model_name) is None:
        return TEMPLATES.TemplateResponse(
            request, "_result.html", {"entry": None, "error": f"Model not found: {model_name}"})
    width, height = _parse_gen_size(size)
    init_bytes = None
    if image is not None:
        data = image.file.read()
        init_bytes = data or None
    gen_req = GenerationRequest(
        model=model_name, prompt=prompt, width=width, height=height,
        steps=steps, seed=seed, negative_prompt=negative_prompt,
        init_image=init_bytes, image_strength=strength,
    )
    job = state.queue.submit(gen_req)
    state.queue.wait(job, timeout=600)
    if job.status != "done":
        return TEMPLATES.TemplateResponse(
            request, "_result.html", {"entry": None, "error": job.error or "failed"})
    entry = None
    for image_bytes in job.result:
        entry = state.history.save(image_bytes, prompt=prompt, model=model_name,
                                   params={"size": size, "steps": steps, "seed": seed,
                                           "image_strength": strength,
                                           "duration": round(job.duration, 2) if job.duration is not None else None})
    return TEMPLATES.TemplateResponse(request, "_result.html", {"entry": entry, "error": None})


@router.post("/admin/repos/download", response_class=HTMLResponse,
             dependencies=[Depends(require_admin)])
def repos_download_ui(request: Request, repo: str = Form(...)):
    repo_id = parse_repo_id(repo)
    job_id = request.app.state.models.start_download_repo(repo_id)
    return TEMPLATES.TemplateResponse(request, "_download.html",
                                      {"job_id": job_id, "repo_id": repo_id,
                                       "status": "running", "error": None})


@router.post("/admin/models/{name}/download-ui", response_class=HTMLResponse,
             dependencies=[Depends(require_admin)])
def model_download_ui(name: str, request: Request):
    try:
        job_id = request.app.state.models.start_download(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Model not found: {name}")
    return TEMPLATES.TemplateResponse(request, "_download.html",
                                      {"job_id": job_id, "repo_id": name,
                                       "status": "running", "error": None})


@router.get("/admin/repos/download/{job_id}", response_class=HTMLResponse,
            dependencies=[Depends(require_admin)])
def repos_download_status_ui(job_id: str, request: Request):
    try:
        st = request.app.state.models.download_status(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Download job not found")
    return TEMPLATES.TemplateResponse(request, "_download.html",
                                      {"job_id": job_id, "repo_id": st.get("repo_id"),
                                       "status": st.get("status"), "error": st.get("error")})


@router.get("/admin/logs", response_class=HTMLResponse)
def logs_page(request: Request):
    redirect = _guard(request)
    if redirect:
        return redirect
    return TEMPLATES.TemplateResponse(request, "logs.html", {})


@router.get("/admin/api/logs", response_class=HTMLResponse,
            dependencies=[Depends(require_admin)])
def logs_tail(request: Request):
    path = getattr(request.app.state, "log_file", None)
    text = ""
    if path:
        p = Path(path)
        if p.exists():
            data = p.read_bytes()[-64 * 1024:]
            lines = data.decode("utf-8", errors="replace").splitlines()
            text = "\n".join(lines[-300:])
    return TEMPLATES.TemplateResponse(request, "_logs.html", {"text": text})
