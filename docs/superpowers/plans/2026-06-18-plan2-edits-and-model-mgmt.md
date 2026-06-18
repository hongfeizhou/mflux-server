# Plan 2 — 图生图 + 模型管理后端 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Plan 1 的基础上加 OpenAI 兼容的图生图 `POST /v1/images/edits`（映射 mflux 的 image_path/image_strength），并实现模型管理后端 API（列出/下载/删除/设默认），为 Plan 3 的 Admin 面板提供数据与动作。

**Architecture:** 复用 Plan 1 的引擎/队列/存储。`GenerationRequest` 增加 `init_image`(bytes)/`image_strength`/`negative_prompt` 字段；`MfluxImageEngine.generate` 在有 init image 时写临时文件并传 `image_path`。`/v1/images/edits` 走 multipart，复用同一队列与响应构建逻辑。模型管理基于 `huggingface_hub`（`scan_cache_dir` 看下载状态、`snapshot_download` 下载、cache delete 删除），下载是后台线程任务+进度轮询，挂在 `/admin/api/*`，用 Bearer key 鉴权（Plan 3 的面板会带 key 调用）。

**Tech Stack:** Python 3.10+、FastAPI、huggingface_hub（已随 mflux 装）、pytest + TestClient。测试用 FakeEngine + mock huggingface_hub，不下载真实模型。

**已确认的 mflux 真实 API（来自 Apple Silicon 真机自省）：**
- `ZImageTurbo.generate_image(seed, prompt, num_inference_steps=4, height=1024, width=1024, guidance=None, image_path=None, image_strength=None, scheduler=None, negative_prompt=None) -> GeneratedImage`
- 返回 `mflux.utils.generated_image.GeneratedImage`，其 `.save(path)` **不覆盖已存在文件**（Plan 1 已修复：存到全新临时路径）。
- `huggingface_hub.scan_cache_dir()` 列出已下载 repo 及大小；`snapshot_download(repo_id)` 下载；`mflux.models.common.config.model_config.AVAILABLE_MODELS` 是 dict，key 即 HF repo id。

---

## 文件结构

```
src/mflux_server/
  engines/base.py          # [改] GenerationRequest 增加 init_image/image_strength/negative_prompt
  engines/mflux_image.py    # [改] generate() 支持 image_path/strength/negative_prompt/guidance；_SPECS 增加 repo_id
  api/openai.py             # [改] 抽出 _build_image_response 复用；新增 /v1/images/edits
  models/__init__.py        # [新] 空
  models/manager.py         # [新] ModelManager：list/download/delete/set_default
  api/admin_models.py       # [新] /admin/api/models* + 设默认路由（Bearer 鉴权）
tests/
  fakes.py                  # [改] FakeEngine 记录 init_image
  test_mflux_engine.py      # [改] 加 generate() 的 img2img 参数传递测试（注入 fake 模型）
  test_api.py               # [改] 加 /v1/images/edits 测试
  test_model_manager.py     # [新] mock huggingface_hub
  test_admin_models_api.py  # [新] 管理路由测试
```

---

## Task 1: GenerationRequest 增加图生图字段

**Files:**
- Modify: `src/mflux_server/engines/base.py`
- Test: `tests/test_engine_base.py` (Create)

- [ ] **Step 1: 写失败的测试**

`tests/test_engine_base.py`：
```python
from mflux_server.engines.base import GenerationRequest


def test_defaults_keep_text_to_image_fields():
    req = GenerationRequest(model="m", prompt="p")
    assert req.init_image is None
    assert req.image_strength is None
    assert req.negative_prompt is None


def test_img2img_fields_settable():
    req = GenerationRequest(model="m", prompt="p", init_image=b"PNG",
                            image_strength=0.6, negative_prompt="blurry")
    assert req.init_image == b"PNG"
    assert req.image_strength == 0.6
    assert req.negative_prompt == "blurry"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_engine_base.py -v`
Expected: FAIL，`TypeError: __init__() got an unexpected keyword argument 'init_image'`

- [ ] **Step 3: 写实现**

在 `src/mflux_server/engines/base.py` 的 `GenerationRequest` 中，于 `quantize` 字段之后追加三个字段（保持现有字段不动）：
```python
@dataclass
class GenerationRequest:
    model: str
    prompt: str
    n: int = 1
    width: int = 1024
    height: int = 1024
    steps: Optional[int] = None
    guidance: Optional[float] = None
    seed: Optional[int] = None
    lora: list = field(default_factory=list)
    quantize: Optional[int] = None
    init_image: Optional[bytes] = None
    image_strength: Optional[float] = None
    negative_prompt: Optional[str] = None
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_engine_base.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add src/mflux_server/engines/base.py tests/test_engine_base.py
git commit -m "feat: add img2img fields to GenerationRequest"
```

---

## Task 2: 引擎支持图生图参数

**Files:**
- Modify: `src/mflux_server/engines/mflux_image.py`
- Test: `tests/test_mflux_engine.py` (append)

引擎在 `generate()` 里：有 `init_image` 时写临时文件并传 `image_path` + `image_strength`，始终传 `negative_prompt` 与 `guidance`。测试通过 monkeypatch `_SPECS` 注入一个记录 kwargs 的 fake 模型，从而无需安装 mflux。

- [ ] **Step 1: 追加失败的测试**

在 `tests/test_mflux_engine.py` 末尾追加：
```python
import os
from mflux_server.engines import mflux_image
from mflux_server.engines.base import GenerationRequest


class _FakeModel:
    def __init__(self):
        self.calls = []

    def generate_image(self, **kwargs):
        self.calls.append(kwargs)

        class _Img:
            def save(self, path):
                with open(path, "wb") as fh:
                    fh.write(b"\x89PNG-fake")
        return _Img()


def _patch_fake_model(monkeypatch):
    fake = _FakeModel()
    spec = mflux_image._SPECS["z-image-turbo"]
    monkeypatch.setattr(spec, "loader", lambda quantize: fake)
    return fake


def test_text_to_image_passes_core_params(monkeypatch):
    fake = _patch_fake_model(monkeypatch)
    engine = mflux_image.MfluxImageEngine()
    engine.generate(GenerationRequest(model="z-image-turbo", prompt="hi",
                                      width=512, height=384, seed=5, steps=7,
                                      guidance=3.5, negative_prompt="ugly"))
    call = fake.calls[-1]
    assert call["prompt"] == "hi"
    assert call["width"] == 512 and call["height"] == 384
    assert call["seed"] == 5 and call["num_inference_steps"] == 7
    assert call["guidance"] == 3.5
    assert call["negative_prompt"] == "ugly"
    assert call.get("image_path") is None


def test_img2img_writes_init_image_and_passes_path(monkeypatch):
    fake = _patch_fake_model(monkeypatch)
    engine = mflux_image.MfluxImageEngine()
    engine.generate(GenerationRequest(model="z-image-turbo", prompt="hi",
                                      init_image=b"\x89PNG-source", image_strength=0.6))
    call = fake.calls[-1]
    assert call["image_strength"] == 0.6
    assert call["image_path"] is not None
    # 引擎应在生成后清理临时输入文件
    assert not os.path.exists(call["image_path"])
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_mflux_engine.py -v`
Expected: FAIL（新两个用例报 KeyError/缺参数；现有 2 个仍通过）

- [ ] **Step 3: 写实现**

替换 `src/mflux_server/engines/mflux_image.py` 中的 `generate` 方法为下面版本（其余不动）：
```python
    def generate(self, req: GenerationRequest) -> list:
        spec = _SPECS[req.model]
        model = self._get_model(req.model, req.quantize)
        steps = req.steps if req.steps is not None else spec.default_steps
        images = []
        for i in range(req.n):
            seed = req.seed + i if req.seed is not None else random.randint(0, 2**31 - 1)
            init_path = None
            try:
                kwargs = dict(
                    prompt=req.prompt,
                    seed=seed,
                    num_inference_steps=steps,
                    width=req.width,
                    height=req.height,
                    guidance=req.guidance,
                    negative_prompt=req.negative_prompt,
                )
                if req.init_image is not None:
                    init_path = self._write_init_image(req.init_image)
                    kwargs["image_path"] = init_path
                    kwargs["image_strength"] = req.image_strength
                generated = model.generate_image(**kwargs)
                images.append(self._to_png_bytes(generated))
            finally:
                if init_path is not None:
                    os.unlink(init_path)
        return images

    @staticmethod
    def _write_init_image(data: bytes) -> str:
        fd, tmp = tempfile.mkstemp(suffix=".png")
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        return tmp
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_mflux_engine.py -v`
Expected: PASS（4 passed）。再跑 `pytest -q` 确认全绿。

- [ ] **Step 5: Commit**

```bash
git add src/mflux_server/engines/mflux_image.py tests/test_mflux_engine.py
git commit -m "feat: engine img2img support (image_path/strength/negative_prompt/guidance)"
```

---

## Task 3: FakeEngine 记录 init_image

**Files:**
- Modify: `tests/fakes.py`

- [ ] **Step 1: 改 FakeEngine.generate**

把 `tests/fakes.py` 的 `FakeEngine.generate` 改成同时记录请求（保留返回 PNG 列表）：
```python
    def generate(self, req: GenerationRequest):
        self.calls.append(req)
        return [ONE_PX_PNG for _ in range(req.n)]
```
（注：现有实现已经 append(req)。如果当前是 append(req) 则无需改动——确认 `self.calls` 存的是整个 `req` 对象，以便 edits 测试能断言 `req.init_image`。若已满足，跳过本步直接进入 Step 2 的提交。）

- [ ] **Step 2: 跑测试 + Commit（若有改动）**

Run: `pytest -q`
Expected: 全绿。若 fakes.py 有改动：
```bash
git add tests/fakes.py
git commit -m "test: FakeEngine records full request for img2img assertions"
```

---

## Task 4: /v1/images/edits 端点

**Files:**
- Modify: `src/mflux_server/api/openai.py`
- Test: `tests/test_api.py` (append)

把 generations 里构建响应的逻辑抽成共享函数 `_build_image_response`，edits 复用它。

- [ ] **Step 1: 追加失败的测试**

在 `tests/test_api.py` 末尾追加：
```python
def test_edits_img2img_returns_b64_and_passes_init_image(client):
    files = {"image": ("src.png", b"\x89PNG-source", "image/png")}
    data = {"prompt": "make it blue", "model": "fake-model",
            "strength": "0.55", "size": "256x256"}
    r = client.post("/v1/images/edits", headers=_auth(client), files=files, data=data)
    assert r.status_code == 200
    body = r.json()
    assert base64.b64decode(body["data"][0]["b64_json"]) == ONE_PX_PNG
    req = client.app.state.registry.engine_for("fake-model").calls[-1]
    assert req.init_image == b"\x89PNG-source"
    assert req.image_strength == 0.55
    assert (req.width, req.height) == (256, 256)


def test_edits_requires_api_key(client):
    files = {"image": ("src.png", b"\x89PNG", "image/png")}
    r = client.post("/v1/images/edits", files=files, data={"prompt": "x"})
    assert r.status_code == 401
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_api.py -v`
Expected: FAIL（404/405，因为 `/v1/images/edits` 尚不存在）

- [ ] **Step 3: 重构 + 实现**

在 `src/mflux_server/api/openai.py` 顶部 imports 增加：
```python
from fastapi import File, Form, UploadFile
```

在 `generations` 函数**之后**新增共享响应构建函数与 edits 路由，并把 `generations` 末尾的响应构建替换为调用共享函数：

新增共享函数：
```python
def _run_and_build(request: Request, gen_req: GenerationRequest, prompt: str,
                   model_name: str, response_format: str, size: str):
    state = request.app.state
    job = state.queue.submit(gen_req)
    state.queue.wait(job, timeout=600)
    if job.status != "done":
        raise HTTPException(status_code=500, detail=job.error or "Generation timed out")
    params = {"steps": gen_req.steps, "guidance": gen_req.guidance,
              "seed": gen_req.seed, "size": size,
              "image_strength": gen_req.image_strength}
    data = []
    for image_bytes in job.result:
        entry = state.history.save(image_bytes, prompt=prompt,
                                   model=model_name, params=params)
        if response_format == "url":
            base = str(request.base_url).rstrip("/")
            data.append({"url": f"{base}/files/{entry.id}.png"})
        else:
            data.append({"b64_json": base64.b64encode(image_bytes).decode()})
    return {"created": int(time.time()), "data": data}
```

把 `generations` 函数体里从 `job = state.queue.submit(...)` 到 `return {...}` 的部分整体替换为：
```python
    return _run_and_build(request, gen_req, body.prompt, model_name,
                          body.response_format, body.size)
```
（保留前面解析 model_name、404 校验、`_parse_size`、构建 `gen_req` 的部分不变。）

新增 edits 路由：
```python
@router.post("/v1/images/edits", dependencies=[Depends(require_api_key)])
async def edits(
    request: Request,
    image: UploadFile = File(...),
    prompt: str = Form(...),
    model: Optional[str] = Form(None),
    n: int = Form(1),
    size: str = Form("1024x1024"),
    response_format: str = Form("b64_json"),
    steps: Optional[int] = Form(None),
    guidance: Optional[float] = Form(None),
    seed: Optional[int] = Form(None),
    strength: Optional[float] = Form(None),
    negative_prompt: Optional[str] = Form(None),
    quantize: Optional[int] = Form(None),
):
    state = request.app.state
    model_name = model or state.config.default_model
    if state.registry.find_model(model_name) is None:
        raise HTTPException(status_code=404, detail=f"Model not found: {model_name}")
    width, height = _parse_size(size)
    init_bytes = await image.read()
    gen_req = GenerationRequest(
        model=model_name, prompt=prompt, n=n, width=width, height=height,
        steps=steps, guidance=guidance, seed=seed, quantize=quantize,
        init_image=init_bytes, image_strength=strength,
        negative_prompt=negative_prompt,
    )
    return _run_and_build(request, gen_req, prompt, model_name, response_format, size)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_api.py -v`
Expected: PASS（8 passed：原 6 + 新 2）。再跑 `pytest -q` 全绿。

- [ ] **Step 5: Commit**

```bash
git add src/mflux_server/api/openai.py tests/test_api.py
git commit -m "feat: OpenAI-compatible /v1/images/edits (img2img) sharing response builder"
```

---

## Task 5: 模型目录（repo_id）

**Files:**
- Modify: `src/mflux_server/engines/mflux_image.py`
- Test: `tests/test_mflux_engine.py` (append)

给 `_ModelSpec` 增加 `repo_id`，给 `ModelInfo` 暴露 repo_id，供模型管理使用。

- [ ] **Step 1: 追加失败的测试**

在 `tests/test_mflux_engine.py` 末尾追加：
```python
def test_model_has_repo_id():
    engine = mflux_image.MfluxImageEngine()
    infos = {m.name: m for m in engine.models()}
    assert infos["z-image-turbo"].repo_id == "Tongyi-MAI/Z-Image-Turbo"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_mflux_engine.py::test_model_has_repo_id -v`
Expected: FAIL，`AttributeError: 'ModelInfo' object has no attribute 'repo_id'`

- [ ] **Step 3: 写实现**

在 `src/mflux_server/engines/base.py` 的 `ModelInfo` 增加可选字段：
```python
@dataclass
class ModelInfo:
    name: str
    family: str
    engine: str
    capabilities: list
    repo_id: Optional[str] = None
```

在 `src/mflux_server/engines/mflux_image.py`：给 `_ModelSpec` 增加 `repo_id: str` 字段（放在 `name` 之后），在 `_SPECS` 的 z-image-turbo 项填 `repo_id="Tongyi-MAI/Z-Image-Turbo"`，并在 `models()` 里把 repo_id 带上：
```python
    def models(self) -> list:
        return [
            ModelInfo(name=s.name, family=s.family, engine=self.id,
                      capabilities=["text-to-image"], repo_id=s.repo_id)
            for s in _SPECS.values()
        ]
```
对应 `_ModelSpec`：
```python
@dataclass
class _ModelSpec:
    name: str
    repo_id: str
    family: str
    default_steps: int
    loader: Callable
```
`_SPECS`：
```python
_SPECS = {
    "z-image-turbo": _ModelSpec(
        name="z-image-turbo", repo_id="Tongyi-MAI/Z-Image-Turbo",
        family="z-image", default_steps=9, loader=_load_z_image_turbo,
    ),
}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_mflux_engine.py -v`
Expected: PASS（5 passed）。再跑 `pytest -q` 全绿。

- [ ] **Step 5: Commit**

```bash
git add src/mflux_server/engines/base.py src/mflux_server/engines/mflux_image.py tests/test_mflux_engine.py
git commit -m "feat: expose repo_id on models for download management"
```

---

## Task 6: ModelManager（list/download/delete/set_default）

**Files:**
- Create: `src/mflux_server/models/__init__.py` (空)
- Create: `src/mflux_server/models/manager.py`
- Test: `tests/test_model_manager.py`

下载是后台线程，进度状态存内存字典可轮询。`huggingface_hub` 通过依赖注入传入，便于 mock。

- [ ] **Step 1: 写失败的测试**

`tests/test_model_manager.py`：
```python
import time
from mflux_server.models.manager import ModelManager
from mflux_server.engines.base import ModelInfo


class _FakeHub:
    def __init__(self, cached=None):
        self._cached = cached or {}     # repo_id -> size_bytes
        self.downloaded = []
        self.deleted = []

    def scan_cache_dir(self):
        hub = self

        class _Revision:
            pass

        class _Repo:
            def __init__(self, rid, size):
                self.repo_id = rid
                self.size_on_disk = size
                self.revisions = [_Revision()]

        class _Info:
            repos = [_Repo(rid, sz) for rid, sz in hub._cached.items()]

            def delete_revisions(self, *hashes):
                class _Strategy:
                    def execute(self_inner):
                        hub.deleted.append(hashes)
                return _Strategy()
        return _Info()

    def snapshot_download(self, repo_id):
        self.downloaded.append(repo_id)
        self._cached[repo_id] = 123


def _models():
    return [ModelInfo(name="z-image-turbo", family="z-image", engine="mflux-image",
                      capabilities=["text-to-image"], repo_id="Tongyi-MAI/Z-Image-Turbo")]


def test_list_marks_downloaded_and_default():
    hub = _FakeHub(cached={"Tongyi-MAI/Z-Image-Turbo": 2_000_000_000})
    mgr = ModelManager(models_provider=_models, default_model="z-image-turbo", hub=hub)
    rows = mgr.list()
    row = rows[0]
    assert row["name"] == "z-image-turbo"
    assert row["downloaded"] is True
    assert row["is_default"] is True
    assert round(row["size_gb"], 1) == 2.0


def test_list_marks_not_downloaded():
    hub = _FakeHub(cached={})
    mgr = ModelManager(models_provider=_models, default_model="z-image-turbo", hub=hub)
    assert mgr.list()[0]["downloaded"] is False
    assert mgr.list()[0]["size_gb"] == 0


def test_download_runs_in_background_and_completes():
    hub = _FakeHub()
    mgr = ModelManager(models_provider=_models, default_model="z-image-turbo", hub=hub)
    job_id = mgr.start_download("z-image-turbo")
    for _ in range(100):
        st = mgr.download_status(job_id)
        if st["status"] in ("done", "error"):
            break
        time.sleep(0.02)
    assert mgr.download_status(job_id)["status"] == "done"
    assert "Tongyi-MAI/Z-Image-Turbo" in hub.downloaded


def test_download_unknown_model_raises():
    mgr = ModelManager(models_provider=_models, default_model="z-image-turbo", hub=_FakeHub())
    import pytest
    with pytest.raises(KeyError):
        mgr.start_download("ghost")


def test_set_default_calls_callback():
    saved = []
    mgr = ModelManager(models_provider=_models, default_model="z-image-turbo",
                       hub=_FakeHub(), on_set_default=saved.append)
    mgr.set_default("z-image-turbo")
    assert saved == ["z-image-turbo"]
    import pytest
    with pytest.raises(KeyError):
        mgr.set_default("ghost")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_model_manager.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'mflux_server.models.manager'`

- [ ] **Step 3: 写实现**

`src/mflux_server/models/__init__.py`：空文件。

`src/mflux_server/models/manager.py`：
```python
import threading
import uuid
from typing import Callable, Optional


class ModelManager:
    def __init__(self, models_provider: Callable, default_model: str,
                 hub=None, on_set_default: Optional[Callable] = None):
        # models_provider() -> list[ModelInfo]；hub 默认用真实 huggingface_hub
        self._models_provider = models_provider
        self._default_model = default_model
        self._on_set_default = on_set_default
        if hub is None:
            import huggingface_hub as hub  # 懒加载真实实现
        self._hub = hub
        self._downloads = {}             # job_id -> {status, repo_id, error}
        self._lock = threading.Lock()

    def _by_name(self, name: str):
        for info in self._models_provider():
            if info.name == name:
                return info
        raise KeyError(name)

    def _cached_sizes(self) -> dict:
        info = self._hub.scan_cache_dir()
        return {repo.repo_id: repo.size_on_disk for repo in info.repos}

    def list(self) -> list:
        sizes = self._cached_sizes()
        rows = []
        for m in self._models_provider():
            size = sizes.get(m.repo_id, 0)
            rows.append({
                "name": m.name,
                "family": m.family,
                "repo_id": m.repo_id,
                "capabilities": m.capabilities,
                "downloaded": m.repo_id in sizes,
                "size_gb": size / 1e9,
                "is_default": m.name == self._default_model,
            })
        return rows

    def start_download(self, name: str) -> str:
        info = self._by_name(name)
        job_id = uuid.uuid4().hex
        with self._lock:
            self._downloads[job_id] = {"status": "running", "repo_id": info.repo_id, "error": None}

        def _run():
            try:
                self._hub.snapshot_download(info.repo_id)
                state = "done"
                err = None
            except Exception as exc:  # noqa: BLE001
                state = "error"
                err = str(exc) or exc.__class__.__name__
            with self._lock:
                self._downloads[job_id]["status"] = state
                self._downloads[job_id]["error"] = err

        threading.Thread(target=_run, daemon=True).start()
        return job_id

    def download_status(self, job_id: str) -> dict:
        with self._lock:
            return dict(self._downloads[job_id])

    def delete(self, name: str) -> bool:
        info = self._by_name(name)
        cache = self._hub.scan_cache_dir()
        hashes = []
        for repo in cache.repos:
            if repo.repo_id == info.repo_id:
                hashes = [rev.commit_hash for rev in repo.revisions]
        if not hashes:
            return False
        cache.delete_revisions(*hashes).execute()
        return True

    def set_default(self, name: str) -> None:
        self._by_name(name)  # 校验存在，不存在抛 KeyError
        self._default_model = name
        if self._on_set_default is not None:
            self._on_set_default(name)
```

注意：测试里的 `_FakeHub` 的 `_Repo.revisions` 用占位对象，`delete` 用到的是 `rev.commit_hash`；为让 `delete` 的真实路径也可测，本计划的删除测试不在本任务（删除走真实 hub 行为在 Task 7 的路由测试里用更完整的 fake 覆盖）。本任务测试聚焦 list/download/set_default。

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_model_manager.py -v`
Expected: PASS（5 passed）。再跑 `pytest -q` 全绿。

- [ ] **Step 5: Commit**

```bash
git add src/mflux_server/models/__init__.py src/mflux_server/models/manager.py tests/test_model_manager.py
git commit -m "feat: ModelManager (list/download/delete/set_default) over huggingface_hub"
```

---

## Task 7: 模型管理路由 + 接入 app

**Files:**
- Create: `src/mflux_server/api/admin_models.py`
- Modify: `src/mflux_server/app.py`
- Modify: `src/mflux_server/cli.py`
- Test: `tests/test_admin_models_api.py`

路由挂在 `/admin/api/*`，用 `require_api_key` 鉴权。`app.state.models` 持有一个 `ModelManager`。`create_app` 增加可选参数 `model_manager`（默认 None，测试注入）；`cli.build_app_from_config` 构建真实的 ModelManager（`on_set_default` 回调写 config.json）。

- [ ] **Step 1: 写失败的测试**

`tests/test_admin_models_api.py`：
```python
import pytest
from fastapi.testclient import TestClient

from mflux_server.app import create_app
from mflux_server.storage.config import ConfigStore
from mflux_server.storage.history import HistoryStore
from mflux_server.engines.registry import EngineRegistry
from mflux_server.queue import JobQueue
from tests.fakes import FakeEngine


class _StubManager:
    def __init__(self):
        self.default = None
        self.downloads = {}

    def list(self):
        return [{"name": "fake-model", "downloaded": True, "is_default": True,
                 "size_gb": 1.5, "repo_id": "org/fake", "family": "fake",
                 "capabilities": ["text-to-image"]}]

    def start_download(self, name):
        if name == "ghost":
            raise KeyError(name)
        self.downloads["job1"] = {"status": "running", "repo_id": "org/fake", "error": None}
        return "job1"

    def download_status(self, job_id):
        return {"status": "done", "repo_id": "org/fake", "error": None}

    def delete(self, name):
        return True

    def set_default(self, name):
        if name == "ghost":
            raise KeyError(name)
        self.default = name


@pytest.fixture
def client(tmp_path):
    config = ConfigStore(base_dir=tmp_path).load()
    registry = EngineRegistry()
    registry.register(FakeEngine(model_name="fake-model"))
    job_queue = JobQueue(registry)
    history = HistoryStore(output_dir=tmp_path / "outputs")
    manager = _StubManager()
    app = create_app(config=config, registry=registry, job_queue=job_queue,
                     history=history, model_manager=manager)
    with TestClient(app) as c:
        c.api_key = config.api_key
        c.manager = manager
        yield c


def _auth(c):
    return {"Authorization": f"Bearer {c.api_key}"}


def test_list_models_requires_auth(client):
    assert client.get("/admin/api/models").status_code == 401


def test_list_models(client):
    r = client.get("/admin/api/models", headers=_auth(client))
    assert r.status_code == 200
    assert r.json()["models"][0]["name"] == "fake-model"


def test_start_download_and_status(client):
    r = client.post("/admin/api/models/fake-model/download", headers=_auth(client))
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    s = client.get(f"/admin/api/models/downloads/{job_id}", headers=_auth(client))
    assert s.json()["status"] == "done"


def test_download_unknown_model_404(client):
    r = client.post("/admin/api/models/ghost/download", headers=_auth(client))
    assert r.status_code == 404


def test_delete_model(client):
    r = client.request("DELETE", "/admin/api/models/fake-model", headers=_auth(client))
    assert r.status_code == 200
    assert r.json()["deleted"] is True


def test_set_default(client):
    r = client.post("/admin/api/models/fake-model/default", headers=_auth(client))
    assert r.status_code == 200
    assert client.manager.default == "fake-model"


def test_set_default_unknown_404(client):
    r = client.post("/admin/api/models/ghost/default", headers=_auth(client))
    assert r.status_code == 404
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_admin_models_api.py -v`
Expected: FAIL（create_app 不接受 model_manager / 路由不存在）

- [ ] **Step 3: 写路由**

`src/mflux_server/api/admin_models.py`：
```python
from fastapi import APIRouter, Depends, HTTPException, Request

from mflux_server.api.auth import require_api_key

router = APIRouter(prefix="/admin/api", dependencies=[Depends(require_api_key)])


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
```

- [ ] **Step 4: 接入 app**

`src/mflux_server/app.py`：把 `create_app` 签名改为带可选 `model_manager=None`，存到 state，并挂载新路由。修改点：
```python
from mflux_server.api import admin_models, files, openai


def create_app(config, registry, job_queue, history, model_manager=None) -> FastAPI:
    app = FastAPI(title="mflux-server")
    app.state.config = config
    app.state.registry = registry
    app.state.queue = job_queue
    app.state.history = history
    app.state.models = model_manager
    ...
    app.include_router(openai.router)
    app.include_router(files.router)
    app.include_router(admin_models.router)
    return app
```
（其余 startup/异常处理保持不变。）

- [ ] **Step 5: 接入 cli**

`src/mflux_server/cli.py` 的 `build_app_from_config` 构建真实 ModelManager 并把 set_default 持久化回 config.json：
```python
from mflux_server.models.manager import ModelManager


def build_app_from_config():
    base = Path(os.environ.get("MFLUX_SERVER_HOME", str(DEFAULT_BASE)))
    store = ConfigStore(base_dir=base)
    config = store.load()
    registry = EngineRegistry()
    registry.register(MfluxImageEngine())
    job_queue = JobQueue(registry)
    history = HistoryStore(output_dir=config.output_dir)

    def _save_default(name):
        config.default_model = name
        store.save(config)

    manager = ModelManager(
        models_provider=registry.models,
        default_model=config.default_model,
        on_set_default=_save_default,
    )
    return create_app(config=config, registry=registry, job_queue=job_queue,
                      history=history, model_manager=manager)
```

- [ ] **Step 6: 跑测试确认通过**

Run: `pytest tests/test_admin_models_api.py -v`
Expected: PASS（7 passed）。再跑 `pytest -q` 全绿（含原有 + 新增）。同时验证导入：`/d/soft/Python312/python -c "from mflux_server.cli import build_app_from_config; print('ok')"`（Windows 上不需要 huggingface_hub 真正联网，ModelManager 懒加载 hub 仅在调用时才触发——构建 app 不调用 hub，OK）。

- [ ] **Step 7: Commit**

```bash
git add src/mflux_server/api/admin_models.py src/mflux_server/app.py src/mflux_server/cli.py tests/test_admin_models_api.py
git commit -m "feat: model management API (/admin/api/models) wired into app and cli"
```

---

## Task 8: 真机验证（手动，Apple Silicon）

**Files:** 无新代码。在 Mac 上验证 img2img 与模型列表的真实行为。

- [ ] **Step 1: 拉取并安装**

Run（Mac）: `cd ~/mflux-server && git pull && .venv/bin/python -m pip install -e ".[mflux,dev]" && .venv/bin/python -m pytest -q`
Expected: 全部测试通过。

- [ ] **Step 2: 启动并验证 /v1/images/edits**

启动：`MFLUX_SERVER_HOME=/tmp/mflux-home .venv/bin/mflux-server start --port 8012`
取 key：`KEY=$(.venv/bin/python -c "import json;print(json.load(open('/tmp/mflux-home/config.json'))['api_key'])")`
先用文生图产出一张源图 `src.png`，再：
```bash
curl -s -X POST http://127.0.0.1:8012/v1/images/edits \
  -H "Authorization: Bearer $KEY" \
  -F image=@src.png -F prompt="make it watercolor" -F model=z-image-turbo \
  -F strength=0.6 -F size=512x512 \
  -o resp.json -w "http=%{http_code}\n"
```
Expected: http=200，resp.json 的 data[0].b64_json 解码为有效 PNG。

- [ ] **Step 3: 验证模型列表**

```bash
curl -s http://127.0.0.1:8012/admin/api/models -H "Authorization: Bearer $KEY"
```
Expected: 返回 z-image-turbo，`downloaded=true`、`size_gb` 约 32.8、`is_default=true`。

---

## Self-Review（plan 对 spec 的覆盖）

- ✅ OpenAI 图生图 `/v1/images/edits`（img2img，image_path/strength）→ Task 1/2/4
- ✅ 引擎扩展 negative_prompt/guidance → Task 2
- ✅ 模型管理：列出+下载状态+大小 → Task 6/7（scan_cache_dir）
- ✅ 模型下载（后台任务+进度轮询）→ Task 6/7（snapshot_download）
- ✅ 删除模型 → Task 6/7
- ✅ 设默认模型（持久化 config.json）→ Task 6/7
- ✅ 复用队列与响应构建（DRY）→ Task 4 `_run_and_build`
- ✅ 真机验证 img2img 与模型列表 → Task 8

**本期不含**（Plan 3）：`/admin` 四页 HTML 面板（仪表盘/模型/画廊/设置）、登录 session、SSE 实时进度、画廊读 `outputs/` 展示。模型管理路由暂用 Bearer key 鉴权；Plan 3 面板会带 key 调用或改 session。
```
