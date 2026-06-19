# Plan 4 — 面板国际化 + 面板内生成 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 Admin 面板加 (1) 国际化：默认英文、可手动切中文（`lang` cookie）；(2) 一个「生成」页，能在面板里直接做文生图与图生图（上传源图 + strength），结果直接显示并进画廊。

**Architecture:** i18n 用 Jinja2 `context_processors` 注入 `t(key)` 与 `lang`（基于 `lang` cookie，默认 `en`），所有模板文案走 `STRINGS` 翻译表；导航栏加 EN/中文 切换链接（`/admin/setlang`）。生成页 `/admin/generate` 是一个表单，POST 到新的 `/admin/api/generate`（session 或 Bearer 鉴权，multipart，支持可选源图）；该端点复用现有队列/引擎/历史，返回一个 HTML 片段（结果图），HTMX 直接 swap 进结果区。

**Tech Stack:** 既有 FastAPI + Jinja2 + HTMX；新增一个翻译模块，无新依赖。测试用 TestClient + FakeEngine。

**复用：** `app.state.queue`（submit/wait）、`app.state.registry`（find_model/engine_for/models）、`app.state.history`（save）、`GenerationRequest`（含 init_image/image_strength/negative_prompt）、`require_admin`、`_guard`。

---

## 文件结构

```
src/mflux_server/admin/
  i18n.py                 # [新] STRINGS + get_lang + translate + i18n_context
  web.py                  # [改] context_processors 接入；setlang 路由；generate 页 + /admin/api/generate
  templates/base.html     # [改] nav 用 t()，加语言切换 + 「生成」入口
  templates/login.html    # [改] t()
  templates/dashboard.html# [改] t()
  templates/_status.html  # [改] t()
  templates/models.html   # [改] t()
  templates/gallery.html  # [改] t()
  templates/settings.html # [改] t()
  templates/generate.html # [新] 生成表单页
  templates/_result.html  # [新] 生成结果片段
tests/
  test_admin_i18n.py      # [新] 语言默认/切换
  test_admin_generate.py  # [新] 面板生成 t2i/img2img
  test_admin_auth.py      # [改] 断言改成英文默认
  test_admin_pages.py     # [改] 断言改成英文默认（或带 lang=zh cookie）
```

---

## Task 1: i18n 基础设施 + 导航/登录翻译

**Files:**
- Create: `src/mflux_server/admin/i18n.py`
- Modify: `src/mflux_server/admin/web.py`（接 context_processors、加 setlang 路由）
- Modify: `templates/base.html`, `templates/login.html`
- Modify: `tests/test_admin_auth.py`
- Test: `tests/test_admin_i18n.py`

- [ ] **Step 1: 写 i18n 模块**

`src/mflux_server/admin/i18n.py`：
```python
SUPPORTED = ("en", "zh")

STRINGS = {
    "nav_dashboard": {"en": "Dashboard", "zh": "仪表盘"},
    "nav_models": {"en": "Models", "zh": "模型"},
    "nav_gallery": {"en": "Gallery", "zh": "画廊"},
    "nav_generate": {"en": "Generate", "zh": "生成"},
    "nav_settings": {"en": "Settings", "zh": "设置"},
    "nav_logout": {"en": "Log out", "zh": "登出"},
    "lang_en": {"en": "EN", "zh": "EN"},
    "lang_zh": {"en": "中文", "zh": "中文"},

    "login_title": {"en": "Sign in", "zh": "登录"},
    "login_placeholder": {"en": "Admin password", "zh": "管理密码"},
    "login_button": {"en": "Sign in", "zh": "登录"},
    "login_error": {"en": "Wrong password", "zh": "密码错误"},

    "dashboard_title": {"en": "Dashboard", "zh": "仪表盘"},
    "st_running": {"en": "Running", "zh": "运行中"},
    "st_queued": {"en": "Queued", "zh": "队列等待"},
    "st_done": {"en": "Completed", "zh": "已完成"},
    "st_history": {"en": "Images", "zh": "历史图片"},
    "st_idle": {"en": "Queue idle", "zh": "队列空闲"},
    "col_task": {"en": "Job", "zh": "任务"},
    "col_status": {"en": "Status", "zh": "状态"},
    "col_model": {"en": "Model", "zh": "模型"},
    "col_prompt": {"en": "Prompt", "zh": "提示词"},

    "models_title": {"en": "Model management", "zh": "模型管理"},
    "col_name": {"en": "Name", "zh": "名称"},
    "col_family": {"en": "Family", "zh": "家族"},
    "col_size": {"en": "Size", "zh": "大小"},
    "col_actions": {"en": "Actions", "zh": "操作"},
    "tag_default": {"en": "default", "zh": "默认"},
    "downloaded": {"en": "Downloaded", "zh": "已下载"},
    "not_downloaded": {"en": "Not downloaded", "zh": "未下载"},
    "btn_download": {"en": "Download", "zh": "下载"},
    "btn_set_default": {"en": "Set default", "zh": "设为默认"},
    "btn_delete": {"en": "Delete", "zh": "删除"},
    "confirm_delete_model": {"en": "Delete local weights for this model?", "zh": "确认删除该模型的本地权重？"},
    "models_hint": {"en": "Downloads run in the background; refresh to see status.",
                     "zh": "下载为后台任务；刷新本页查看最新状态。"},

    "gallery_title": {"en": "Gallery / History", "zh": "画廊 / 历史"},
    "gallery_empty": {"en": "No generations yet.", "zh": "还没有生成记录。"},
    "btn_regenerate": {"en": "Re-generate", "zh": "重新生成"},
    "btn_download_file": {"en": "Download", "zh": "下载"},
    "confirm_delete_image": {"en": "Delete this image?", "zh": "删除这张？"},

    "settings_title": {"en": "Settings", "zh": "设置"},
    "settings_apikey": {"en": "API Key", "zh": "API Key"},
    "btn_reset_key": {"en": "Reset key", "zh": "重置 Key"},
    "confirm_reset_key": {"en": "The old key stops working immediately. Continue?",
                           "zh": "重置后旧 Key 立即失效，确认？"},
    "settings_sdk_hint": {"en": "In the OpenAI SDK use this key with",
                           "zh": "在 OpenAI SDK 里用此 Key 搭配"},
    "settings_defaults": {"en": "Generation defaults", "zh": "生成默认"},
    "lbl_default_model": {"en": "Default model", "zh": "默认模型"},
    "lbl_default_steps": {"en": "Default steps", "zh": "默认步数"},
    "lbl_bind": {"en": "Bind address", "zh": "监听地址"},
    "lbl_output": {"en": "Output dir", "zh": "输出目录"},

    "generate_title": {"en": "Generate", "zh": "生成"},
    "lbl_prompt": {"en": "Prompt", "zh": "提示词"},
    "lbl_model": {"en": "Model", "zh": "模型"},
    "lbl_size": {"en": "Size", "zh": "尺寸"},
    "lbl_steps": {"en": "Steps (optional)", "zh": "步数（可选）"},
    "lbl_seed": {"en": "Seed (optional)", "zh": "种子（可选）"},
    "lbl_negative": {"en": "Negative prompt (optional)", "zh": "反向提示词（可选）"},
    "lbl_image": {"en": "Source image (optional, for img2img)", "zh": "源图（可选，用于图生图）"},
    "lbl_strength": {"en": "Strength", "zh": "强度"},
    "btn_generate": {"en": "Generate", "zh": "生成"},
    "generate_hint": {"en": "Leave source image empty for text-to-image; add one for image-to-image.",
                       "zh": "不传源图为文生图；上传源图为图生图。"},
    "generating": {"en": "Generating…", "zh": "生成中…"},
    "generate_failed": {"en": "Generation failed", "zh": "生成失败"},
}


def get_lang(request) -> str:
    lang = request.cookies.get("lang", "en")
    return lang if lang in SUPPORTED else "en"


def translate(lang: str, key: str) -> str:
    entry = STRINGS.get(key)
    if not entry:
        return key
    return entry.get(lang) or entry.get("en") or key


def i18n_context(request) -> dict:
    lang = get_lang(request)
    return {"lang": lang, "t": lambda key: translate(lang, key)}
```

- [ ] **Step 2: 写失败的测试 `tests/test_admin_i18n.py`**

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
def app(tmp_path):
    config = ConfigStore(base_dir=tmp_path).load()
    registry = EngineRegistry()
    registry.register(FakeEngine(model_name="fake-model"))
    job_queue = JobQueue(registry)
    history = HistoryStore(output_dir=tmp_path / "outputs")
    return create_app(config=config, registry=registry, job_queue=job_queue,
                      history=history, model_manager=None)


def test_login_default_english(app):
    with TestClient(app) as c:
        r = c.get("/admin/login")
        assert "Sign in" in r.text
        assert "登录" not in r.text


def test_login_chinese_with_cookie(app):
    with TestClient(app) as c:
        c.cookies.set("lang", "zh")
        r = c.get("/admin/login")
        assert "登录" in r.text


def test_setlang_sets_cookie_and_redirects(app):
    with TestClient(app) as c:
        r = c.get("/admin/setlang?code=zh&next=/admin/login", follow_redirects=False)
        assert r.status_code in (302, 307)
        assert r.headers["location"] == "/admin/login"
        # cookie 已设置为 zh
        assert c.cookies.get("lang") == "zh"


def test_setlang_rejects_unknown_code(app):
    with TestClient(app) as c:
        c.get("/admin/setlang?code=fr&next=/admin/login")
        # 非法语言不写入（保持默认 en）
        r = c.get("/admin/login")
        assert "Sign in" in r.text
```

- [ ] **Step 3: 接入 web.py + setlang 路由**

在 `src/mflux_server/admin/web.py`：
- import：`from fastapi.responses import HTMLResponse, RedirectResponse`（已存在）；新增 `from mflux_server.admin.i18n import i18n_context, SUPPORTED`。
- 把 `TEMPLATES = Jinja2Templates(directory=...)` 改为带 context processor：
```python
TEMPLATES = Jinja2Templates(
    directory=str(Path(__file__).parent / "templates"),
    context_processors=[i18n_context],
)
```
- 新增路由：
```python
@router.get("/admin/setlang")
def setlang(request: Request, code: str = "en", next: str = "/admin"):
    resp = RedirectResponse(url=next, status_code=302)
    if code in SUPPORTED:
        resp.set_cookie("lang", code, max_age=31536000, httponly=False, samesite="lax")
    return resp
```

- [ ] **Step 4: 翻译 base.html / login.html**

`templates/base.html` 的 nav 改为：
```html
  {% if show_nav is not defined or show_nav %}
  <nav class="nav">
    <span class="brand">mflux-server</span>
    <a href="/admin">{{ t('nav_dashboard') }}</a>
    <a href="/admin/generate">{{ t('nav_generate') }}</a>
    <a href="/admin/models">{{ t('nav_models') }}</a>
    <a href="/admin/gallery">{{ t('nav_gallery') }}</a>
    <a href="/admin/settings">{{ t('nav_settings') }}</a>
    <span class="right">
      {% if lang == 'zh' %}<a href="/admin/setlang?code=en&next=/admin">{{ t('lang_en') }}</a>
      {% else %}<a href="/admin/setlang?code=zh&next=/admin">{{ t('lang_zh') }}</a>{% endif %}
      &nbsp;·&nbsp;<a href="/admin/logout">{{ t('nav_logout') }}</a>
    </span>
  </nav>
  {% endif %}
```
（注：`/admin/generate` 链接 Task 3 才有页面，但导航先放上无妨。）

`templates/login.html`：
```html
{% extends "base.html" %}
{% block title %}{{ t('login_title') }}{% endblock %}
{% set show_nav = False %}
{% block content %}
<div class="login">
  <h1>mflux-server</h1>
  {% if error %}<p class="err">{{ t('login_error') }}</p>{% endif %}
  <form method="post" action="/admin/login">
    <input type="password" name="password" placeholder="{{ t('login_placeholder') }}" autofocus>
    <button type="submit">{{ t('login_button') }}</button>
  </form>
</div>
{% endblock %}
```
注意：`login_submit` 在密码错误时传的是 `{"error": "密码错误"}`——改为传一个布尔，让模板用 `t('login_error')`。把 `web.py` 的 `login_submit` 失败分支改为：
```python
    return TEMPLATES.TemplateResponse(
        request, "login.html", {"error": True}, status_code=401)
```

- [ ] **Step 5: 更新 test_admin_auth.py 断言（英文默认）**

`tests/test_admin_auth.py` 的 `test_login_page_renders` 当前断言 `"password" in r.text.lower()`——英文 placeholder "Admin password" 仍含 "password"，**该用例无需改**。其余用例不依赖具体文案。确认 `pytest tests/test_admin_auth.py -v` 仍 5 passed；若有因文案变化而失败的断言，就地改成英文对应词。

- [ ] **Step 6: 跑测试**

Run: `pytest tests/test_admin_i18n.py tests/test_admin_auth.py -v`
Expected: i18n 4 passed + auth 5 passed。再 `pytest -q` —— 注意此时 `test_admin_pages.py` 里断言中文（如「仪表盘」「队列」）的用例会因英文默认而失败，那是 **Task 2** 修复的，本任务允许 test_admin_pages 暂时红。但其余必须绿。**实现者：** 本任务只需保证 test_admin_i18n + test_admin_auth 通过；如果 `pytest -q` 因 test_admin_pages 标红，确认失败仅来自 test_admin_pages 的中文断言即可，不要去改 test_admin_pages（留给 Task 2）。

- [ ] **Step 7: Commit**

```bash
git add src/mflux_server/admin/i18n.py src/mflux_server/admin/web.py src/mflux_server/admin/templates/base.html src/mflux_server/admin/templates/login.html tests/test_admin_i18n.py tests/test_admin_auth.py
git commit -m "feat: admin panel i18n (English default, Chinese toggle) + login/nav"
```

---

## Task 2: 翻译其余页面 + 修复断言

**Files:**
- Modify: `templates/dashboard.html`, `_status.html`, `models.html`, `gallery.html`, `settings.html`
- Modify: `tests/test_admin_pages.py`（断言改英文默认）

- [ ] **Step 1: 翻译模板**

`templates/dashboard.html`：
```html
{% extends "base.html" %}
{% block title %}{{ t('dashboard_title') }}{% endblock %}
{% block content %}
<h1>{{ t('dashboard_title') }}</h1>
<div id="status" hx-get="/admin/api/status" hx-trigger="load, every 2s">{{ t('generating') }}</div>
{% endblock %}
```

`templates/_status.html`：
```html
<div class="row" style="gap:24px">
  <div class="card" style="flex:1"><div class="muted">{{ t('st_running') }}</div><div style="font-size:24px">{{ running|length }}</div></div>
  <div class="card" style="flex:1"><div class="muted">{{ t('st_queued') }}</div><div style="font-size:24px">{{ queued|length }}</div></div>
  <div class="card" style="flex:1"><div class="muted">{{ t('st_done') }}</div><div style="font-size:24px">{{ done }}</div></div>
  <div class="card" style="flex:1"><div class="muted">{{ t('st_history') }}</div><div style="font-size:24px">{{ total_history }}</div></div>
</div>
{% if running or queued %}
<div class="card">
  <table>
    <tr><th>{{ t('col_task') }}</th><th>{{ t('col_status') }}</th><th>{{ t('col_model') }}</th><th>{{ t('col_prompt') }}</th></tr>
    {% for j in running + queued %}
    <tr><td>{{ j.id[:8] }}</td><td><span class="tag">{{ j.status }}</span></td>
        <td>{{ j.request.model }}</td><td class="muted">{{ j.request.prompt[:40] }}</td></tr>
    {% endfor %}
  </table>
</div>
{% else %}<p class="muted">{{ t('st_idle') }}</p>{% endif %}
```

`templates/models.html`：
```html
{% extends "base.html" %}
{% block title %}{{ t('nav_models') }}{% endblock %}
{% block content %}
<h1>{{ t('models_title') }}</h1>
<div class="card">
<table>
  <tr><th>{{ t('col_name') }}</th><th>{{ t('col_family') }}</th><th>{{ t('col_status') }}</th><th>{{ t('col_size') }}</th><th>{{ t('col_actions') }}</th></tr>
  {% for m in models %}
  <tr id="model-{{ m.name }}">
    <td>{{ m.name }} {% if m.is_default %}<span class="tag">{{ t('tag_default') }}</span>{% endif %}</td>
    <td class="muted">{{ m.family }}</td>
    <td>{% if m.downloaded %}{{ t('downloaded') }}{% else %}<span class="muted">{{ t('not_downloaded') }}</span>{% endif %}</td>
    <td class="muted">{% if m.size_gb %}{{ "%.1f"|format(m.size_gb) }} GB{% else %}-{% endif %}</td>
    <td class="row">
      {% if not m.downloaded %}
      <button class="btn" hx-post="/admin/api/models/{{ m.name }}/download" hx-swap="none">{{ t('btn_download') }}</button>
      {% endif %}
      <button class="btn" hx-post="/admin/api/models/{{ m.name }}/default" hx-swap="none">{{ t('btn_set_default') }}</button>
      {% if m.downloaded %}
      <button class="btn danger" hx-delete="/admin/api/models/{{ m.name }}"
              hx-confirm="{{ t('confirm_delete_model') }}" hx-swap="none">{{ t('btn_delete') }}</button>
      {% endif %}
    </td>
  </tr>
  {% endfor %}
</table>
</div>
<p class="muted">{{ t('models_hint') }}</p>
{% endblock %}
```

`templates/gallery.html`：
```html
{% extends "base.html" %}
{% block title %}{{ t('nav_gallery') }}{% endblock %}
{% block content %}
<h1>{{ t('gallery_title') }}</h1>
{% if not entries %}<p class="muted">{{ t('gallery_empty') }}</p>{% endif %}
<div class="grid">
  {% for e in entries %}
  <figure id="hist-{{ e.id }}">
    <a href="/files/{{ e.id }}.png" target="_blank"><img src="/files/{{ e.id }}.png" alt=""></a>
    <figcaption>
      <div>{{ e.prompt[:60] }}</div>
      <div class="muted">{{ e.model }}</div>
      <div class="row" style="margin-top:6px">
        <button class="btn" hx-post="/admin/api/history/{{ e.id }}/rerun" hx-swap="none">{{ t('btn_regenerate') }}</button>
        <a class="btn" href="/files/{{ e.id }}.png" download>{{ t('btn_download_file') }}</a>
        <button class="btn danger" hx-delete="/admin/api/history/{{ e.id }}"
                hx-target="closest figure" hx-swap="delete"
                hx-confirm="{{ t('confirm_delete_image') }}">{{ t('btn_delete') }}</button>
      </div>
    </figcaption>
  </figure>
  {% endfor %}
</div>
{% endblock %}
```

`templates/settings.html`：
```html
{% extends "base.html" %}
{% block title %}{{ t('nav_settings') }}{% endblock %}
{% block content %}
<h1>{{ t('settings_title') }}</h1>
<div class="card">
  <h3>{{ t('settings_apikey') }}</h3>
  <p><code id="key">{{ cfg.api_key }}</code></p>
  <button class="btn" hx-post="/admin/api/regenerate-key" hx-swap="none"
          hx-confirm="{{ t('confirm_reset_key') }}"
          hx-on::after-request="location.reload()">{{ t('btn_reset_key') }}</button>
  <p class="muted">{{ t('settings_sdk_hint') }} <code>base_url=http://{{ cfg.host }}:{{ cfg.port }}/v1</code></p>
</div>
<div class="card">
  <h3>{{ t('settings_defaults') }}</h3>
  <table>
    <tr><td>{{ t('lbl_default_model') }}</td><td>{{ cfg.default_model }}</td></tr>
    <tr><td>{{ t('lbl_default_steps') }}</td><td>{{ cfg.default_steps }}</td></tr>
    <tr><td>{{ t('lbl_bind') }}</td><td>{{ cfg.host }}:{{ cfg.port }}</td></tr>
    <tr><td>{{ t('lbl_output') }}</td><td class="muted">{{ cfg.output_dir }}</td></tr>
  </table>
</div>
{% endblock %}
```

- [ ] **Step 2: 修 test_admin_pages.py 断言**

把依赖中文 UI 文案的断言改为英文默认：
- `test_dashboard_renders`: `assert "仪表盘" in r.text` → `assert "Dashboard" in r.text`
- `test_status_fragment_shows_counts`: `assert "队列" in r.text or "历史" in r.text` → `assert "Queued" in r.text or "Images" in r.text`
其余断言（断言模型名 "z-image-turbo"、画廊里 prompt 文本 "a unicorn"、状态码等）是数据不是 UI 文案，**不要改**。

- [ ] **Step 3: 跑测试**

Run: `pytest tests/test_admin_pages.py -v`
Expected: 9 passed。再 `pytest -q` 全绿。

- [ ] **Step 4: Commit**

```bash
git add src/mflux_server/admin/templates/dashboard.html src/mflux_server/admin/templates/_status.html src/mflux_server/admin/templates/models.html src/mflux_server/admin/templates/gallery.html src/mflux_server/admin/templates/settings.html tests/test_admin_pages.py
git commit -m "feat: translate dashboard/models/gallery/settings templates"
```

---

## Task 3: 生成页 + /admin/api/generate（文生图 + 图生图）

**Files:**
- Modify: `src/mflux_server/admin/web.py`
- Create: `templates/generate.html`, `templates/_result.html`
- Test: `tests/test_admin_generate.py`

- [ ] **Step 1: 写失败的测试 `tests/test_admin_generate.py`**

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
def client(tmp_path):
    config = ConfigStore(base_dir=tmp_path).load()
    registry = EngineRegistry()
    registry.register(FakeEngine(model_name="z-image-turbo"))
    job_queue = JobQueue(registry)
    history = HistoryStore(output_dir=tmp_path / "outputs")
    app = create_app(config=config, registry=registry, job_queue=job_queue,
                     history=history, model_manager=None)
    with TestClient(app) as c:
        c.post("/admin/login", data={"password": config.admin_password})
        yield c


def test_generate_page_renders(client):
    r = client.get("/admin/generate")
    assert r.status_code == 200
    assert 'name="prompt"' in r.text


def test_generate_page_redirects_anonymous(client):
    fresh = TestClient(client.app)
    assert fresh.get("/admin/generate", follow_redirects=False).status_code in (302, 307)


def test_generate_text_to_image(client):
    r = client.post("/admin/api/generate",
                    data={"prompt": "a blue car", "model": "z-image-turbo", "size": "256x256"})
    assert r.status_code == 200
    assert "/files/" in r.text                      # 返回结果图片片段
    req = client.app.state.registry.engine_for("z-image-turbo").calls[-1]
    assert req.prompt == "a blue car"
    assert req.init_image is None
    assert len(client.app.state.history.list()) == 1


def test_generate_img2img(client):
    files = {"image": ("src.png", b"\x89PNG-source", "image/png")}
    data = {"prompt": "watercolor", "model": "z-image-turbo", "size": "256x256", "strength": "0.6"}
    r = client.post("/admin/api/generate", files=files, data=data)
    assert r.status_code == 200
    req = client.app.state.registry.engine_for("z-image-turbo").calls[-1]
    assert req.init_image == b"\x89PNG-source"
    assert req.image_strength == 0.6


def test_generate_requires_auth(client):
    fresh = TestClient(client.app)
    assert fresh.post("/admin/api/generate", data={"prompt": "x"}).status_code == 401
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_admin_generate.py -v`
Expected: FAIL（页面/端点不存在）

- [ ] **Step 3: 实现路由（web.py）**

在 `src/mflux_server/admin/web.py`：
- imports 增加：`from fastapi import File, Form, UploadFile`（与现有 fastapi import 合并）、`from typing import Optional`、`from mflux_server.engines.base import GenerationRequest`。（`Depends`、`require_admin`、`HTMLResponse`、`Request` 已在。）
- 新增页面与端点：
```python
@router.get("/admin/generate", response_class=HTMLResponse)
def generate_page(request: Request):
    redirect = _guard(request)
    if redirect:
        return redirect
    models = request.app.state.registry.models()
    return TEMPLATES.TemplateResponse(request, "generate.html", {"models": models})


def _parse_size(size: str):
    try:
        w, h = size.lower().split("x")
        return int(w), int(h)
    except (ValueError, AttributeError):
        return 1024, 1024


@router.post("/admin/api/generate", response_class=HTMLResponse,
             dependencies=[Depends(require_admin)])
async def generate_action(
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
    width, height = _parse_size(size)
    init_bytes = None
    if image is not None:
        data = await image.read()
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
                                           "image_strength": strength})
    return TEMPLATES.TemplateResponse(request, "_result.html", {"entry": entry, "error": None})
```

- [ ] **Step 4: 模板**

`templates/generate.html`：
```html
{% extends "base.html" %}
{% block title %}{{ t('generate_title') }}{% endblock %}
{% block content %}
<h1>{{ t('generate_title') }}</h1>
<div class="card">
  <form hx-post="/admin/api/generate" hx-target="#result" hx-swap="innerHTML"
        hx-encoding="multipart/form-data" hx-indicator="#gen-ind">
    <p><label>{{ t('lbl_prompt') }}</label><br>
       <textarea name="prompt" rows="3" style="width:100%" class="field" required></textarea></p>
    <div class="row">
      <label>{{ t('lbl_model') }}
        <select name="model" class="field">
          {% for m in models %}<option value="{{ m.name }}">{{ m.name }}</option>{% endfor %}
        </select>
      </label>
      <label>{{ t('lbl_size') }} <input name="size" value="1024x1024" class="field" style="width:120px"></label>
      <label>{{ t('lbl_steps') }} <input name="steps" type="number" class="field" style="width:80px"></label>
      <label>{{ t('lbl_seed') }} <input name="seed" type="number" class="field" style="width:110px"></label>
    </div>
    <p><label>{{ t('lbl_negative') }}<br>
       <input name="negative_prompt" class="field" style="width:100%"></label></p>
    <div class="row">
      <label>{{ t('lbl_image') }} <input name="image" type="file" accept="image/*"></label>
      <label>{{ t('lbl_strength') }} <input name="strength" type="number" step="0.05" min="0" max="1" value="0.6" class="field" style="width:90px"></label>
    </div>
    <p><button class="btn" type="submit">{{ t('btn_generate') }}</button>
       <span id="gen-ind" class="htmx-indicator muted">{{ t('generating') }}</span></p>
  </form>
  <p class="muted">{{ t('generate_hint') }}</p>
</div>
<div id="result"></div>
{% endblock %}
```

`templates/_result.html`：
```html
{% if entry %}
<figure class="card">
  <a href="/files/{{ entry.id }}.png" target="_blank"><img src="/files/{{ entry.id }}.png" style="max-width:100%;border-radius:8px"></a>
  <figcaption class="muted">{{ entry.prompt[:80] }}</figcaption>
</figure>
{% else %}
<p class="err">{{ t('generate_failed') }}: {{ error }}</p>
{% endif %}
```

- [ ] **Step 5: 跑测试确认通过**

Run: `pytest tests/test_admin_generate.py -v`
Expected: 5 passed。再 `pytest -q` 全绿。

- [ ] **Step 6: Commit**

```bash
git add src/mflux_server/admin/web.py src/mflux_server/admin/templates/generate.html src/mflux_server/admin/templates/_result.html tests/test_admin_generate.py
git commit -m "feat: in-panel generate page (text-to-image + img2img)"
```

---

## Task 4: 真机验证（手动，Apple Silicon）

**Files:** 无新代码。

- [ ] **Step 1: 拉取 + 测试**

Run（Mac）: `cd ~/mflux-server && git pull && .venv/bin/python -m pytest -q`
Expected: 全绿。

- [ ] **Step 2: 重启常驻实例并验证**

重启 8800 实例（见运维说明），浏览器验证：
- `/admin/login` 默认英文；点「中文」后界面变中文（cookie 生效）。
- 进「Generate / 生成」页，输入提示词点生成 → 结果图直接显示；刷新 Gallery 能看到。
- 上传一张源图 + strength 生成 → 得到 img2img 结果。

curl 冒烟（文生图经面板端点，需先登录拿 cookie）：
```bash
PW=$(python3 -c "import json,os;print(json.load(open(os.path.expanduser('~/.mflux-server/config.json')))['admin_password'])")
curl -s -c /tmp/cj -d "password=$PW" http://127.0.0.1:8800/admin/login -o /dev/null
curl -s -b /tmp/cj -F prompt="a small boat" -F model=z-image-turbo -F size=384x384 \
  http://127.0.0.1:8800/admin/api/generate | grep -o "/files/[a-f0-9]*\.png" | head -1
```
Expected: 打印一个 `/files/<id>.png`（生成成功）。

---

## Self-Review（plan 对需求的覆盖）

- ✅ 面板默认英文 → i18n_context 默认 `en`（Task 1）
- ✅ 可手动切中文（cookie + 导航切换）→ setlang 路由 + nav 链接（Task 1）
- ✅ 全部页面文案翻译 → Task 1（login/nav）+ Task 2（其余页）
- ✅ 面板内文生图 → 生成页 + /admin/api/generate（Task 3）
- ✅ 面板内图生图 → 同端点支持上传源图 + strength（Task 3）
- ✅ 结果直接显示 + 进画廊 → _result.html 片段 + history.save（Task 3）
- ✅ 真机验证 → Task 4

**不含：** 自动按浏览器语言判断（按约定走手动切换）；生成进度条/流式（HTMX indicator 简单提示即可，生成同步阻塞返回）。
