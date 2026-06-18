# Plan 3 — Admin 面板 UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Plan 1/2 的后端之上，做出 `/admin` Web 面板：登录 + 仪表盘 + 模型管理 + 画廊/历史 + 设置四个页面，给单机单用户管理这个图像服务。

**Architecture:** 服务端渲染（Jinja2）+ vendored HTMX 做局部刷新，登录用 Starlette `SessionMiddleware`（用 config.api_key 作签名密钥）签发 session cookie。`/admin/api/*` 改为「session 或 Bearer key 任一通过」即可（面板用 cookie 调，外部脚本仍可用 Bearer）。HTML 页面未登录则重定向到 `/admin/login`。仪表盘实时进度用 HTMX 每 2 秒轮询 `/admin/api/status` 拉取片段（替代 SSE，单用户足够且可测）。

**Tech Stack:** FastAPI、Jinja2（新增核心依赖）、Starlette SessionMiddleware、vendored htmx.min.js、手写精简 CSS。测试用 TestClient（cookie 跟随）。无 Node 构建。

**对原 spec 的务实调整：** (1) 实时进度 SSE → HTMX 轮询 `/admin/api/status`；(2) 样式用手写 `app.css` 而非 Tailwind 构建。两者都不影响功能，且保持离线、零构建。

**复用的已有后端：**
- `app.state.config`（api_key, admin_password, host, port, default_model, default_steps, output_dir）
- `app.state.queue`（`list()` → Job{id,status,created_at,request}）、`app.state.registry`、`app.state.history`（`list()/get(id)/delete(id)/image_path(id)`，HistoryEntry{id,prompt,model,params,created_at}）、`app.state.models`（ModelManager：list/start_download/download_status/delete/set_default）
- 路由：`/v1/images/generations|edits`、`/v1/models`、`/files/{id}.png`、`/admin/api/models*`
- `mflux_server.api.auth.require_api_key`（Bearer）

---

## 文件结构

```
src/mflux_server/
  admin/__init__.py            # [新] 空
  admin/auth.py                # [新] is_authed / require_admin（session 或 bearer）
  admin/web.py                 # [新] HTML 页面路由 + 登录/登出 + /admin/api/status 片段
  admin/history_api.py         # [新] /admin/api/history（list/delete/rerun）
  admin/templates/base.html    # [新] 布局
  admin/templates/login.html
  admin/templates/dashboard.html
  admin/templates/_status.html # [新] 仪表盘轮询片段
  admin/templates/models.html
  admin/templates/gallery.html
  admin/templates/settings.html
  admin/static/app.css         # [新] 精简样式
  admin/static/htmx.min.js     # [新] vendored（实现时下载）
  api/admin_models.py          # [改] 鉴权由 require_api_key → require_admin
  app.py                       # [改] 加 SessionMiddleware、Jinja2、StaticFiles、挂 web/history 路由
pyproject.toml                 # [改] dependencies 加 jinja2
tests/
  test_admin_auth.py           # [新] 登录/会话/重定向
  test_admin_pages.py          # [新] 四个页面渲染 + status 片段
  test_admin_history_api.py    # [新] 历史 list/delete/rerun
  test_admin_models_api.py     # [改] 用 session 也能访问（补一个用例）
```

---

## Task 1: Web 基础设施 + 登录/会话

**Files:**
- Create: `src/mflux_server/admin/__init__.py`（空）, `src/mflux_server/admin/auth.py`, `src/mflux_server/admin/web.py`
- Create templates: `base.html`, `login.html`, `dashboard.html`（占位，Task 4 完善）
- Create: `src/mflux_server/admin/static/app.css`, `src/mflux_server/admin/static/htmx.min.js`
- Modify: `pyproject.toml`（加 jinja2）, `src/mflux_server/app.py`
- Test: `tests/test_admin_auth.py`

- [ ] **Step 1: 加依赖 + 下载 vendored htmx**

在 `pyproject.toml` 的 `dependencies` 列表加 `"jinja2>=3.1"`。重新安装：`/d/soft/Python312/python -m pip install -e ".[dev]"`。

下载 htmx 到 static（PowerShell，单文件，离线用）：
```
Invoke-WebRequest -Uri "https://unpkg.com/htmx.org@1.9.12/dist/htmx.min.js" -OutFile "D:\www\mflux-server\src\mflux_server\admin\static\htmx.min.js" -UseBasicParsing
```
若下载失败，写一个占位文件（内容 `// htmx placeholder`）保证打包不缺文件，并在报告中注明需后续补真实 htmx。

- [ ] **Step 2: 写失败的测试 `tests/test_admin_auth.py`**

```python
import pytest
from fastapi.testclient import TestClient

from mflux_server.app import create_app
from mflux_server.storage.config import ConfigStore
from mflux_server.storage.history import HistoryStore
from mflux_server.engines.registry import EngineRegistry
from mflux_server.queue import JobQueue
from tests.fakes import FakeEngine


@pytest.fixture
def ctx(tmp_path):
    config = ConfigStore(base_dir=tmp_path).load()
    registry = EngineRegistry()
    registry.register(FakeEngine(model_name="fake-model"))
    job_queue = JobQueue(registry)
    history = HistoryStore(output_dir=tmp_path / "outputs")
    app = create_app(config=config, registry=registry, job_queue=job_queue,
                     history=history, model_manager=None)
    return app, config


def test_login_page_renders(ctx):
    app, _ = ctx
    with TestClient(app) as c:
        r = c.get("/admin/login")
        assert r.status_code == 200
        assert "password" in r.text.lower()


def test_protected_page_redirects_to_login_when_anonymous(ctx):
    app, _ = ctx
    with TestClient(app) as c:
        r = c.get("/admin", follow_redirects=False)
        assert r.status_code in (302, 307)
        assert "/admin/login" in r.headers["location"]


def test_login_wrong_password_rejected(ctx):
    app, _ = ctx
    with TestClient(app) as c:
        r = c.post("/admin/login", data={"password": "wrong"}, follow_redirects=False)
        assert r.status_code in (401, 200)
        # 仍未登录：访问受保护页应被重定向
        assert c.get("/admin", follow_redirects=False).status_code in (302, 307)


def test_login_correct_password_grants_session(ctx):
    app, config = ctx
    with TestClient(app) as c:
        r = c.post("/admin/login", data={"password": config.admin_password},
                   follow_redirects=False)
        assert r.status_code in (302, 307)
        # 登录后可访问仪表盘
        assert c.get("/admin").status_code == 200


def test_logout_clears_session(ctx):
    app, config = ctx
    with TestClient(app) as c:
        c.post("/admin/login", data={"password": config.admin_password})
        c.get("/admin/logout", follow_redirects=False)
        assert c.get("/admin", follow_redirects=False).status_code in (302, 307)
```

- [ ] **Step 3: 写 auth `src/mflux_server/admin/auth.py`**

```python
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
    # 供 /admin/api/* 使用：session 或 Bearer 任一通过
    if not is_authed(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
```

- [ ] **Step 4: 写 web 路由 `src/mflux_server/admin/web.py`**

```python
import secrets as _secrets
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from mflux_server.admin.auth import is_authed

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
router = APIRouter()


def _guard(request: Request):
    # 页面级守卫：未登录返回重定向响应；已登录返回 None
    if not is_authed(request):
        return RedirectResponse(url="/admin/login", status_code=302)
    return None


@router.get("/admin/login", response_class=HTMLResponse)
def login_page(request: Request):
    return TEMPLATES.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/admin/login")
def login_submit(request: Request, password: str = Form(...)):
    expected = request.app.state.config.admin_password
    if _secrets.compare_digest(password, expected):
        request.session["authed"] = True
        return RedirectResponse(url="/admin", status_code=302)
    return TEMPLATES.TemplateResponse(
        "login.html", {"request": request, "error": "密码错误"}, status_code=401)


@router.get("/admin/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/admin/login", status_code=302)


@router.get("/admin", response_class=HTMLResponse)
def dashboard(request: Request):
    redirect = _guard(request)
    if redirect:
        return redirect
    return TEMPLATES.TemplateResponse("dashboard.html", {"request": request})
```

- [ ] **Step 5: base.html / login.html / dashboard.html（占位）/ app.css**

`src/mflux_server/admin/templates/base.html`：
```html
<!doctype html>
<html lang="zh">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>mflux-server · {% block title %}{% endblock %}</title>
  <link rel="stylesheet" href="/admin/static/app.css">
  <script src="/admin/static/htmx.min.js" defer></script>
</head>
<body>
  {% if show_nav is not defined or show_nav %}
  <nav class="nav">
    <span class="brand">mflux-server</span>
    <a href="/admin">仪表盘</a>
    <a href="/admin/models">模型</a>
    <a href="/admin/gallery">画廊</a>
    <a href="/admin/settings">设置</a>
    <a class="right" href="/admin/logout">登出</a>
  </nav>
  {% endif %}
  <main class="main">{% block content %}{% endblock %}</main>
</body>
</html>
```

`login.html`：
```html
{% extends "base.html" %}
{% block title %}登录{% endblock %}
{% set show_nav = False %}
{% block content %}
<div class="login">
  <h1>mflux-server</h1>
  {% if error %}<p class="err">{{ error }}</p>{% endif %}
  <form method="post" action="/admin/login">
    <input type="password" name="password" placeholder="管理密码" autofocus>
    <button type="submit">登录</button>
  </form>
</div>
{% endblock %}
```

`dashboard.html`（Task 4 完善，先占位可渲染）：
```html
{% extends "base.html" %}
{% block title %}仪表盘{% endblock %}
{% block content %}
<h1>仪表盘</h1>
<div id="status">加载中…</div>
{% endblock %}
```

`src/mflux_server/admin/static/app.css`：
```css
:root { --bg:#0f1115; --panel:#181b22; --fg:#e6e6e6; --muted:#9aa4b2; --accent:#4f8cff; --border:#272b34; }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--fg); font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif; }
.nav { display:flex; gap:16px; align-items:center; padding:12px 20px; background:var(--panel); border-bottom:1px solid var(--border); }
.nav a { color:var(--muted); text-decoration:none; }
.nav a:hover { color:var(--fg); }
.nav .brand { font-weight:600; color:var(--fg); margin-right:12px; }
.nav .right { margin-left:auto; }
.main { padding:24px; max-width:1100px; margin:0 auto; }
h1 { font-size:20px; margin:0 0 16px; }
.login { max-width:320px; margin:12vh auto; text-align:center; }
.login input, .login button { width:100%; padding:10px; margin:6px 0; border-radius:8px; border:1px solid var(--border); background:var(--panel); color:var(--fg); }
.login button, button.btn { background:var(--accent); border:none; color:#fff; cursor:pointer; }
.err { color:#ff6b6b; }
.card { background:var(--panel); border:1px solid var(--border); border-radius:12px; padding:16px; margin-bottom:16px; }
table { width:100%; border-collapse:collapse; }
th, td { text-align:left; padding:8px 10px; border-bottom:1px solid var(--border); }
.muted { color:var(--muted); }
.grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(160px,1fr)); gap:12px; }
.grid figure { margin:0; background:var(--panel); border:1px solid var(--border); border-radius:10px; overflow:hidden; }
.grid img { width:100%; height:160px; object-fit:cover; display:block; }
.grid figcaption { padding:8px; font-size:12px; }
button.btn { padding:6px 12px; border-radius:8px; }
button.danger { background:#3a2326; color:#ff8a8a; }
.row { display:flex; gap:8px; align-items:center; }
.tag { font-size:12px; padding:2px 8px; border-radius:999px; background:#22303f; color:#8fb7ff; }
input.field, select.field { padding:8px; border-radius:8px; border:1px solid var(--border); background:var(--bg); color:var(--fg); }
```

- [ ] **Step 6: 改 `src/mflux_server/app.py` 装配面板**

在 imports 增加：
```python
from pathlib import Path
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from mflux_server.admin import web as admin_web
```
在 `create_app` 里（设置完 state、加异常处理器之后，include 路由处）加入：
```python
    app.add_middleware(SessionMiddleware, secret_key=config.api_key)
    _static = Path(__file__).parent / "admin" / "static"
    app.mount("/admin/static", StaticFiles(directory=str(_static)), name="admin-static")
    app.include_router(admin_web.router)
```
注意：`SessionMiddleware` 用 `config.api_key` 作签名密钥；StaticFiles 目录用绝对路径。其余不变。

- [ ] **Step 7: 跑测试**

Run: `pytest tests/test_admin_auth.py -v`
Expected: PASS（5 passed）。再 `pytest -q` 全绿。

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml src/mflux_server/admin src/mflux_server/app.py tests/test_admin_auth.py
git commit -m "feat: admin web infra, session login, base layout/css"
```

---

## Task 2: /admin/api 改用 session-或-bearer 鉴权

**Files:**
- Modify: `src/mflux_server/api/admin_models.py`
- Test: `tests/test_admin_models_api.py`（追加 session 用例）

- [ ] **Step 1: 追加失败的测试**

在 `tests/test_admin_models_api.py` 末尾追加（登录拿 session 后用 cookie 访问，无 Bearer）：
```python
def test_list_models_via_session_cookie(client):
    # 未登录无 key -> 401
    assert client.get("/admin/api/models").status_code == 401
    # 登录拿到 session cookie（client fixture 的 config.admin_password）
    pw = client.app.state.config.admin_password
    client.post("/admin/login", data={"password": pw})
    r = client.get("/admin/api/models")  # 仅靠 cookie
    assert r.status_code == 200
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_admin_models_api.py::test_list_models_via_session_cookie -v`
Expected: FAIL（当前 require_api_key 不认 session，返回 401）

- [ ] **Step 3: 改鉴权**

在 `src/mflux_server/api/admin_models.py`：把
```python
from mflux_server.api.auth import require_api_key
...
router = APIRouter(prefix="/admin/api", dependencies=[Depends(require_api_key)])
```
改为
```python
from mflux_server.admin.auth import require_admin
...
router = APIRouter(prefix="/admin/api", dependencies=[Depends(require_admin)])
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_admin_models_api.py -v`
Expected: PASS（原 7 + 新 1 = 8 passed；Bearer 路径仍通过，因为 require_admin 也认 Bearer）。再 `pytest -q` 全绿。

- [ ] **Step 5: Commit**

```bash
git add src/mflux_server/api/admin_models.py tests/test_admin_models_api.py
git commit -m "feat: admin api accepts session or bearer auth"
```

---

## Task 3: 历史 API（list/delete/rerun）

**Files:**
- Create: `src/mflux_server/admin/history_api.py`
- Modify: `src/mflux_server/app.py`（挂路由）
- Test: `tests/test_admin_history_api.py`

- [ ] **Step 1: 写失败的测试 `tests/test_admin_history_api.py`**

```python
import base64
import pytest
from fastapi.testclient import TestClient

from mflux_server.app import create_app
from mflux_server.storage.config import ConfigStore
from mflux_server.storage.history import HistoryStore
from mflux_server.engines.registry import EngineRegistry
from mflux_server.queue import JobQueue
from tests.fakes import FakeEngine, ONE_PX_PNG


@pytest.fixture
def client(tmp_path):
    config = ConfigStore(base_dir=tmp_path).load()
    registry = EngineRegistry()
    registry.register(FakeEngine(model_name="fake-model"))
    job_queue = JobQueue(registry)
    history = HistoryStore(output_dir=tmp_path / "outputs")
    app = create_app(config=config, registry=registry, job_queue=job_queue,
                     history=history, model_manager=None)
    with TestClient(app) as c:
        c.api_key = config.api_key
        yield c


def _auth(c):
    return {"Authorization": f"Bearer {c.api_key}"}


def _seed(client, prompt="a cat"):
    return client.app.state.history.save(ONE_PX_PNG, prompt=prompt,
                                         model="fake-model", params={"size": "256x256"})


def test_history_list(client):
    _seed(client, "a")
    _seed(client, "b")
    r = client.get("/admin/api/history", headers=_auth(client))
    assert r.status_code == 200
    assert len(r.json()["items"]) == 2


def test_history_list_requires_auth(client):
    assert client.get("/admin/api/history").status_code == 401


def test_history_delete(client):
    e = _seed(client)
    r = client.request("DELETE", f"/admin/api/history/{e.id}", headers=_auth(client))
    assert r.status_code == 200 and r.json()["deleted"] is True
    assert client.get("/admin/api/history", headers=_auth(client)).json()["items"] == []


def test_history_rerun_resubmits(client):
    e = _seed(client, "a robot")
    r = client.post(f"/admin/api/history/{e.id}/rerun", headers=_auth(client))
    assert r.status_code == 200
    # 引擎应被再次调用，prompt 一致
    req = client.app.state.registry.engine_for("fake-model").calls[-1]
    assert req.prompt == "a robot"


def test_history_rerun_unknown_404(client):
    r = client.post("/admin/api/history/nope/rerun", headers=_auth(client))
    assert r.status_code == 404
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_admin_history_api.py -v`
Expected: FAIL（路由不存在）

- [ ] **Step 3: 写 `src/mflux_server/admin/history_api.py`**

```python
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
```

- [ ] **Step 4: 挂路由**

在 `src/mflux_server/app.py`：import `from mflux_server.admin import history_api`，并 `app.include_router(history_api.router)`（与其他 include 放一起）。

- [ ] **Step 5: 跑测试确认通过**

Run: `pytest tests/test_admin_history_api.py -v`
Expected: PASS（5 passed）。再 `pytest -q` 全绿。

- [ ] **Step 6: Commit**

```bash
git add src/mflux_server/admin/history_api.py src/mflux_server/app.py tests/test_admin_history_api.py
git commit -m "feat: admin history API (list/delete/rerun)"
```

---

## Task 4: 仪表盘页面 + 状态轮询片段

**Files:**
- Modify: `src/mflux_server/admin/web.py`（加 `/admin/api/status` + 完善 dashboard 渲染数据）
- Create: `src/mflux_server/admin/templates/_status.html`
- Modify: `src/mflux_server/admin/templates/dashboard.html`
- Test: `tests/test_admin_pages.py`（创建，含 dashboard + status）

- [ ] **Step 1: 写失败的测试 `tests/test_admin_pages.py`**

```python
import pytest
from fastapi.testclient import TestClient

from mflux_server.app import create_app
from mflux_server.storage.config import ConfigStore
from mflux_server.storage.history import HistoryStore
from mflux_server.engines.registry import EngineRegistry
from mflux_server.queue import JobQueue
from tests.fakes import FakeEngine, ONE_PX_PNG


class _StubManager:
    def list(self):
        return [{"name": "z-image-turbo", "downloaded": True, "is_default": True,
                 "size_gb": 32.8, "repo_id": "Tongyi-MAI/Z-Image-Turbo",
                 "family": "z-image", "capabilities": ["text-to-image"]}]


@pytest.fixture
def client(tmp_path):
    config = ConfigStore(base_dir=tmp_path).load()
    registry = EngineRegistry()
    registry.register(FakeEngine(model_name="z-image-turbo"))
    job_queue = JobQueue(registry)
    history = HistoryStore(output_dir=tmp_path / "outputs")
    app = create_app(config=config, registry=registry, job_queue=job_queue,
                     history=history, model_manager=_StubManager())
    with TestClient(app) as c:
        c.post("/admin/login", data={"password": config.admin_password})
        yield c


def test_dashboard_renders(client):
    r = client.get("/admin")
    assert r.status_code == 200
    assert "仪表盘" in r.text


def test_status_fragment_shows_counts(client):
    client.app.state.history.save(ONE_PX_PNG, prompt="x", model="z-image-turbo", params={})
    r = client.get("/admin/api/status")
    assert r.status_code == 200
    # 片段含队列与历史计数
    assert "队列" in r.text or "queue" in r.text.lower()


def test_status_requires_auth(client):
    fresh = TestClient(client.app)
    assert fresh.get("/admin/api/status").status_code == 401
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_admin_pages.py -v`
Expected: FAIL（/admin/api/status 不存在）

- [ ] **Step 3: 加 status 路由 + 完善 dashboard**

在 `src/mflux_server/admin/web.py` 增加（顶部已 import APIRouter/Request/HTMLResponse/TEMPLATES/is_authed；再 import require_admin 与 Depends）：
```python
from fastapi import Depends
from mflux_server.admin.auth import require_admin


@router.get("/admin/api/status", response_class=HTMLResponse,
            dependencies=[Depends(require_admin)])
def status_fragment(request: Request):
    state = request.app.state
    jobs = state.queue.list()
    running = [j for j in jobs if j.status == "running"]
    queued = [j for j in jobs if j.status == "queued"]
    total_history = len(state.history.list())
    return TEMPLATES.TemplateResponse("_status.html", {
        "request": request,
        "running": running, "queued": queued,
        "done": len([j for j in jobs if j.status == "done"]),
        "errored": len([j for j in jobs if j.status == "error"]),
        "total_history": total_history,
    })
```
把 `dashboard` 路由的渲染上下文补上模型信息（如果 `app.state.models` 为 None 则空列表）：
```python
@router.get("/admin", response_class=HTMLResponse)
def dashboard(request: Request):
    redirect = _guard(request)
    if redirect:
        return redirect
    models = request.app.state.models.list() if request.app.state.models else []
    return TEMPLATES.TemplateResponse("dashboard.html",
                                      {"request": request, "models": models})
```

`src/mflux_server/admin/templates/_status.html`：
```html
<div class="row" style="gap:24px">
  <div class="card" style="flex:1"><div class="muted">运行中</div><div style="font-size:24px">{{ running|length }}</div></div>
  <div class="card" style="flex:1"><div class="muted">队列等待</div><div style="font-size:24px">{{ queued|length }}</div></div>
  <div class="card" style="flex:1"><div class="muted">已完成</div><div style="font-size:24px">{{ done }}</div></div>
  <div class="card" style="flex:1"><div class="muted">历史图片</div><div style="font-size:24px">{{ total_history }}</div></div>
</div>
{% if running or queued %}
<div class="card">
  <table>
    <tr><th>任务</th><th>状态</th><th>模型</th><th>提示词</th></tr>
    {% for j in running + queued %}
    <tr><td>{{ j.id[:8] }}</td><td><span class="tag">{{ j.status }}</span></td>
        <td>{{ j.request.model }}</td><td class="muted">{{ j.request.prompt[:40] }}</td></tr>
    {% endfor %}
  </table>
</div>
{% else %}<p class="muted">队列空闲</p>{% endif %}
```

`src/mflux_server/admin/templates/dashboard.html`：
```html
{% extends "base.html" %}
{% block title %}仪表盘{% endblock %}
{% block content %}
<h1>仪表盘</h1>
<div id="status" hx-get="/admin/api/status" hx-trigger="load, every 2s">加载中…</div>
{% endblock %}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_admin_pages.py -v`
Expected: PASS（3 passed）。再 `pytest -q` 全绿。

- [ ] **Step 5: Commit**

```bash
git add src/mflux_server/admin/web.py src/mflux_server/admin/templates/_status.html src/mflux_server/admin/templates/dashboard.html tests/test_admin_pages.py
git commit -m "feat: dashboard page with HTMX status polling"
```

---

## Task 5: 模型管理页面

**Files:**
- Modify: `src/mflux_server/admin/web.py`（加 `/admin/models`）
- Create: `src/mflux_server/admin/templates/models.html`
- Test: `tests/test_admin_pages.py`（追加）

- [ ] **Step 1: 追加失败的测试**

```python
def test_models_page_lists_models(client):
    r = client.get("/admin/models")
    assert r.status_code == 200
    assert "z-image-turbo" in r.text


def test_models_page_redirects_anonymous(client):
    fresh = TestClient(client.app)
    assert fresh.get("/admin/models", follow_redirects=False).status_code in (302, 307)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_admin_pages.py -k models -v`
Expected: FAIL（404，页面未实现）

- [ ] **Step 3: 加路由 + 模板**

`src/mflux_server/admin/web.py` 增加：
```python
@router.get("/admin/models", response_class=HTMLResponse)
def models_page(request: Request):
    redirect = _guard(request)
    if redirect:
        return redirect
    models = request.app.state.models.list() if request.app.state.models else []
    return TEMPLATES.TemplateResponse("models.html", {"request": request, "models": models})
```

`src/mflux_server/admin/templates/models.html`：
```html
{% extends "base.html" %}
{% block title %}模型{% endblock %}
{% block content %}
<h1>模型管理</h1>
<div class="card">
<table>
  <tr><th>名称</th><th>家族</th><th>状态</th><th>大小</th><th>操作</th></tr>
  {% for m in models %}
  <tr id="model-{{ m.name }}">
    <td>{{ m.name }} {% if m.is_default %}<span class="tag">默认</span>{% endif %}</td>
    <td class="muted">{{ m.family }}</td>
    <td>{% if m.downloaded %}已下载{% else %}<span class="muted">未下载</span>{% endif %}</td>
    <td class="muted">{% if m.size_gb %}{{ "%.1f"|format(m.size_gb) }} GB{% else %}-{% endif %}</td>
    <td class="row">
      {% if not m.downloaded %}
      <button class="btn" hx-post="/admin/api/models/{{ m.name }}/download"
              hx-swap="none">下载</button>
      {% endif %}
      <button class="btn" hx-post="/admin/api/models/{{ m.name }}/default"
              hx-swap="none">设为默认</button>
      {% if m.downloaded %}
      <button class="btn danger" hx-delete="/admin/api/models/{{ m.name }}"
              hx-confirm="确认删除 {{ m.name }} 的本地权重？" hx-swap="none">删除</button>
      {% endif %}
    </td>
  </tr>
  {% endfor %}
</table>
</div>
<p class="muted">下载为后台任务；下载/删除/设默认后刷新本页查看最新状态。</p>
{% endblock %}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_admin_pages.py -v`
Expected: PASS（5 passed）。再 `pytest -q` 全绿。

- [ ] **Step 5: Commit**

```bash
git add src/mflux_server/admin/web.py src/mflux_server/admin/templates/models.html tests/test_admin_pages.py
git commit -m "feat: models management page (download/delete/set-default via HTMX)"
```

---

## Task 6: 画廊/历史页面

**Files:**
- Modify: `src/mflux_server/admin/web.py`（加 `/admin/gallery`）
- Create: `src/mflux_server/admin/templates/gallery.html`
- Test: `tests/test_admin_pages.py`（追加）

- [ ] **Step 1: 追加失败的测试**

```python
def test_gallery_shows_history(client):
    client.app.state.history.save(ONE_PX_PNG, prompt="a unicorn",
                                  model="z-image-turbo", params={"size": "256x256"})
    r = client.get("/admin/gallery")
    assert r.status_code == 200
    assert "a unicorn" in r.text
    assert "/files/" in r.text


def test_gallery_empty_renders(client):
    r = client.get("/admin/gallery")
    assert r.status_code == 200
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_admin_pages.py -k gallery -v`
Expected: FAIL（404）

- [ ] **Step 3: 加路由 + 模板**

`src/mflux_server/admin/web.py` 增加：
```python
@router.get("/admin/gallery", response_class=HTMLResponse)
def gallery_page(request: Request):
    redirect = _guard(request)
    if redirect:
        return redirect
    entries = request.app.state.history.list()
    return TEMPLATES.TemplateResponse("gallery.html", {"request": request, "entries": entries})
```

`src/mflux_server/admin/templates/gallery.html`：
```html
{% extends "base.html" %}
{% block title %}画廊{% endblock %}
{% block content %}
<h1>画廊 / 历史</h1>
{% if not entries %}<p class="muted">还没有生成记录。</p>{% endif %}
<div class="grid">
  {% for e in entries %}
  <figure id="hist-{{ e.id }}">
    <a href="/files/{{ e.id }}.png" target="_blank"><img src="/files/{{ e.id }}.png" alt=""></a>
    <figcaption>
      <div>{{ e.prompt[:60] }}</div>
      <div class="muted">{{ e.model }}</div>
      <div class="row" style="margin-top:6px">
        <button class="btn" hx-post="/admin/api/history/{{ e.id }}/rerun" hx-swap="none">重新生成</button>
        <a class="btn" href="/files/{{ e.id }}.png" download>下载</a>
        <button class="btn danger" hx-delete="/admin/api/history/{{ e.id }}"
                hx-target="#hist-{{ e.id }}" hx-swap="outerHTML"
                hx-confirm="删除这张？">删除</button>
      </div>
    </figcaption>
  </figure>
  {% endfor %}
</div>
{% endblock %}
```
说明：删除按钮用 `hx-target/#hist-{id}` + `hx-swap=outerHTML`，后端 DELETE 返回的 JSON 会替换该卡片为 JSON 文本——为更干净，可让 DELETE 在 HTMX 删除场景返回空串。**实现时**：保持 `history_api.delete_history` 返回 JSON 不变（API 契约），画廊里删除后用 `hx-swap="delete"` 更合适——把删除按钮的 `hx-swap` 改为 `delete`，并去掉 `hx-target` 改为 `hx-target="closest figure"`：
```html
        <button class="btn danger" hx-delete="/admin/api/history/{{ e.id }}"
                hx-target="closest figure" hx-swap="delete"
                hx-confirm="删除这张？">删除</button>
```
（用上面这版按钮。）

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_admin_pages.py -v`
Expected: PASS（7 passed）。再 `pytest -q` 全绿。

- [ ] **Step 5: Commit**

```bash
git add src/mflux_server/admin/web.py src/mflux_server/admin/templates/gallery.html tests/test_admin_pages.py
git commit -m "feat: gallery/history page (view/rerun/download/delete)"
```

---

## Task 7: 设置页面 + 重置 API Key

**Files:**
- Modify: `src/mflux_server/admin/web.py`（加 `/admin/settings` + `/admin/api/regenerate-key`）
- Create: `src/mflux_server/admin/templates/settings.html`
- Test: `tests/test_admin_pages.py`（追加）

设置页展示 api_key、默认模型/步数、host/port、output_dir，并能重置 api_key（写回 config.json）。重置 key 需通过注入的持久化回调，避免 web 层直接依赖 ConfigStore。

- [ ] **Step 1: 追加失败的测试**

```python
def test_settings_shows_api_key(client):
    r = client.get("/admin/settings")
    assert r.status_code == 200
    assert client.app.state.config.api_key in r.text


def test_regenerate_key_changes_key(client):
    old = client.app.state.config.api_key
    r = client.post("/admin/api/regenerate-key")
    assert r.status_code == 200
    assert client.app.state.config.api_key != old
    assert r.json()["api_key"] == client.app.state.config.api_key
```

注意：`regenerate-key` 改了 api_key 也就改了 session 签名密钥；但 SessionMiddleware 在 app 创建时已绑定旧 api_key，进程内中间件密钥不变，所以当前 session 仍有效——可接受（重启后用新 key 签名）。测试里 fixture 已登录，调用后仍是已登录态。

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_admin_pages.py -k "settings or regenerate" -v`
Expected: FAIL（404）

- [ ] **Step 3: app/cli 注入配置持久化回调**

为让重置 key 能写回磁盘，`create_app` 增加可选参数 `on_config_change=None` 存到 `app.state.on_config_change`。修改 `src/mflux_server/app.py` 的 `create_app` 签名与 state：
```python
def create_app(config, registry, job_queue, history, model_manager=None,
               on_config_change=None) -> FastAPI:
    ...
    app.state.on_config_change = on_config_change
```
`src/mflux_server/cli.py` 的 `build_app_from_config` 里传入：在 `_save_default` 旁边加一个保存整个 config 的回调，并传给 create_app：
```python
    def _save_config():
        store.save(config)

    manager = ModelManager(
        models_provider=registry.models,
        default_model=config.default_model,
        on_set_default=_save_default,
    )
    return create_app(config=config, registry=registry, job_queue=job_queue,
                      history=history, model_manager=manager,
                      on_config_change=_save_config)
```

- [ ] **Step 4: 加路由 + 模板**

`src/mflux_server/admin/web.py` 增加（用到 secrets，已 import 为 `_secrets`）：
```python
@router.get("/admin/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    redirect = _guard(request)
    if redirect:
        return redirect
    return TEMPLATES.TemplateResponse("settings.html",
                                      {"request": request, "cfg": request.app.state.config})


@router.post("/admin/api/regenerate-key", dependencies=[Depends(require_admin)])
def regenerate_key(request: Request):
    config = request.app.state.config
    config.api_key = "sk-" + _secrets.token_hex(24)
    if request.app.state.on_config_change:
        request.app.state.on_config_change()
    return {"api_key": config.api_key}
```

`src/mflux_server/admin/templates/settings.html`：
```html
{% extends "base.html" %}
{% block title %}设置{% endblock %}
{% block content %}
<h1>设置</h1>
<div class="card">
  <h3>API Key</h3>
  <p><code id="key">{{ cfg.api_key }}</code></p>
  <button class="btn" hx-post="/admin/api/regenerate-key" hx-target="#key"
          hx-swap="innerHTML" hx-confirm="重置后旧 Key 立即失效，确认？"
          hx-on::after-request="if(event.detail.successful){this.previousElementSibling.querySelector('code').textContent=JSON.parse(event.detail.xhr.responseText).api_key}">
    重置 Key
  </button>
  <p class="muted">在 OpenAI SDK 里用 <code>base_url=http://{{ cfg.host }}:{{ cfg.port }}/v1</code> + 此 Key。</p>
</div>
<div class="card">
  <h3>生成默认</h3>
  <table>
    <tr><td>默认模型</td><td>{{ cfg.default_model }}</td></tr>
    <tr><td>默认步数</td><td>{{ cfg.default_steps }}</td></tr>
    <tr><td>监听地址</td><td>{{ cfg.host }}:{{ cfg.port }}</td></tr>
    <tr><td>输出目录</td><td class="muted">{{ cfg.output_dir }}</td></tr>
  </table>
</div>
{% endblock %}
```
说明：上面重置按钮用 `hx-swap="innerHTML"` 直接把 `#key` 内容替换为返回的 JSON 文本即可（最简）。为显示干净，把 `hx-target` 设为 `#key` 且让返回值就是 key 文本更好——**实现时采用更简单可靠的版本**：让按钮 `hx-post` 后用 `hx-target="#key" hx-swap="innerHTML"`，并把 `regenerate_key` 的返回从 JSON 改为对 HTMX 友好？不——API 要返回 JSON 供脚本用。因此模板里去掉复杂的 `hx-on`，改为：点击后整页可手动刷新查看新 key，或用最小内联脚本。为通过测试（断言新 key 出现在 JSON 响应）与可用性，按钮保留 `hx-post="/admin/api/regenerate-key" hx-swap="none"` 并在其后加一行说明「重置后刷新本页查看新 Key」。最终按钮：
```html
  <button class="btn" hx-post="/admin/api/regenerate-key" hx-swap="none"
          hx-confirm="重置后旧 Key 立即失效，确认？"
          hx-on::after-request="location.reload()">重置 Key</button>
```

- [ ] **Step 5: 跑测试确认通过**

Run: `pytest tests/test_admin_pages.py -v`
Expected: PASS（9 passed）。再 `pytest -q` 全绿。

- [ ] **Step 6: Commit**

```bash
git add src/mflux_server/admin/web.py src/mflux_server/admin/templates/settings.html src/mflux_server/app.py src/mflux_server/cli.py tests/test_admin_pages.py
git commit -m "feat: settings page + API key regeneration"
```

---

## Task 8: 真机验证（手动，Apple Silicon）

**Files:** 无新代码。在 Mac 上验证面板可用。

- [ ] **Step 1: 拉取 + 安装 + 测试**

Run（Mac）: `cd ~/mflux-server && git pull && .venv/bin/python -m pip install -e ".[mflux,dev]" && .venv/bin/python -m pytest -q`
Expected: 全绿。

- [ ] **Step 2: 启动并验证面板**

`MFLUX_SERVER_HOME=/tmp/mflux-home .venv/bin/mflux-server start --port 8013`
用浏览器或 curl 验证：
- `GET /admin/login` 返回 200、含密码框
- 用 `admin_password`（启动日志/config.json）POST 登录拿 cookie
- 带 cookie：`GET /admin`、`/admin/models`、`/admin/gallery`、`/admin/settings` 均 200
- `GET /admin/api/status` 返回片段含计数
- 在画廊先经由 `/v1/images/generations` 产出几张图后应能看到

curl 冒烟示例：
```bash
PW=$(.venv/bin/python -c "import json;print(json.load(open('/tmp/mflux-home/config.json'))['admin_password'])")
curl -s -c /tmp/cj.txt -d "password=$PW" http://127.0.0.1:8013/admin/login -o /dev/null -w "login=%{http_code}\n"
for p in /admin /admin/models /admin/gallery /admin/settings /admin/api/status; do
  curl -s -b /tmp/cj.txt http://127.0.0.1:8013$p -o /dev/null -w "$p=%{http_code}\n"
done
```
Expected: login=302，其余各页=200。

---

## Self-Review（plan 对 spec 的覆盖）

- ✅ Admin 面板登录（session）→ Task 1
- ✅ 仪表盘 + 实时进度（HTMX 轮询替代 SSE）→ Task 4
- ✅ 模型管理页（下载/删除/设默认，调 Plan 2 API）→ Task 5
- ✅ 画廊/历史（浏览/重新生成/下载/删除）→ Task 3（API）+ Task 6（页面）
- ✅ 设置 + API Key 查看/重置 → Task 7
- ✅ `/admin/api/*` 支持 session 或 Bearer → Task 2
- ✅ 真机验证 → Task 8

**对 spec 的务实偏差（已在抬头说明）：** SSE → HTMX 轮询；Tailwind 构建 → 手写精简 CSS + vendored HTMX。功能等价、离线、零 Node 构建。
**不含：** 面板内的「从零发起生成」表单（生成走 OpenAI API/SDK 或画廊「重新生成」）；多用户/权限（单用户）。
```
