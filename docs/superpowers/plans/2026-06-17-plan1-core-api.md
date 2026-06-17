# Plan 1 — 核心 API（文生图服务）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 mflux 封装成一个本地运行的 OpenAI 兼容文生图服务：`POST /v1/images/generations` + `GET /v1/models`，带 Bearer 鉴权、内存任务队列、文件存储，CLI 一条命令启动。

**Architecture:** 单进程 FastAPI 应用。OpenAI 端点把请求转成内部 `GenerationRequest`，提交到内存中的单 worker 任务队列串行执行（Apple Silicon 一次只跑一个模型），端点阻塞等待结果再按 OpenAI 格式返回。引擎层抽象（`BaseEngine` + `EngineRegistry`），本期实现 `MfluxImageEngine`，为视频引擎预留扩展点。配置和生成历史用纯文件存储（`~/.mflux-server/`），无数据库。

**Tech Stack:** Python 3.10+、FastAPI、uvicorn、pydantic、mflux（可选依赖，仅 macOS/Apple Silicon）。测试用 pytest + FastAPI TestClient（mock 引擎，不跑真实模型）。

---

## 文件结构

```
mflux-server/
  pyproject.toml                      # 包定义 + 依赖 + 入口命令
  .gitignore
  src/mflux_server/
    __init__.py
    storage/config.py                 # Config + ConfigStore (config.json)
    storage/history.py                # HistoryEntry + HistoryStore (outputs/)
    engines/base.py                   # GenerationRequest, ModelInfo, BaseEngine
    engines/registry.py               # EngineRegistry
    engines/mflux_image.py            # MfluxImageEngine（懒加载 mflux）
    queue.py                          # Job + JobQueue（单 worker 线程）
    api/auth.py                       # require_api_key 依赖
    api/openai.py                     # /v1 路由 + 参数映射 + 错误格式
    api/files.py                      # GET /files/{id}.png
    app.py                            # create_app() 装配
    cli.py                            # mflux-server start
  tests/
    test_config.py
    test_history.py
    test_engine_registry.py
    test_queue.py
    test_api.py
    fakes.py                          # FakeEngine + 1x1 PNG 常量
```

各文件单一职责：`storage/*` 只管文件读写；`engines/*` 只管"模型名→生成字节"；`queue.py` 只管串行调度；`api/*` 只管 HTTP 协议与 OpenAI 格式；`app.py` 只做装配。

---

## Task 1: 项目脚手架

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `src/mflux_server/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: 写 pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "mflux-server"
version = "0.1.0"
description = "OpenAI-compatible image generation server wrapping mflux (Apple Silicon)"
requires-python = ">=3.10"
dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "pydantic>=2.5",
    "python-multipart>=0.0.9",
]

[project.optional-dependencies]
mflux = ["mflux"]
dev = ["pytest>=8", "httpx>=0.27"]

[project.scripts]
mflux-server = "mflux_server.cli:main"

[tool.hatch.build.targets.wheel]
packages = ["src/mflux_server"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

注意：`mflux` 是**可选依赖**，因为它只装得上 Apple Silicon Mac。核心代码和测试不直接 import mflux（引擎里懒加载），所以测试在任意平台都能跑。

- [ ] **Step 2: 写 .gitignore**

```gitignore
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
build/
dist/
.venv/
```

- [ ] **Step 3: 建空的包文件**

`src/mflux_server/__init__.py`：
```python
__version__ = "0.1.0"
```

`tests/__init__.py`：（空文件）

- [ ] **Step 4: 安装并验证 pytest 能跑**

Run: `pip install -e ".[dev]"` 然后 `pytest -q`
Expected: 安装成功；pytest 输出 `no tests ran`（没有测试，但命令成功退出）

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .gitignore src/mflux_server/__init__.py tests/__init__.py
git commit -m "chore: project scaffold with pyproject and package layout"
```

---

## Task 2: 配置存储（ConfigStore）

**Files:**
- Create: `src/mflux_server/storage/__init__.py`（空）
- Create: `src/mflux_server/storage/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: 写失败的测试**

`tests/test_config.py`：
```python
from pathlib import Path
from mflux_server.storage.config import ConfigStore


def test_load_creates_config_with_generated_api_key(tmp_path: Path):
    store = ConfigStore(base_dir=tmp_path)
    cfg = store.load()
    assert cfg.api_key.startswith("sk-")
    assert (tmp_path / "config.json").exists()
    assert cfg.output_dir == str(tmp_path / "outputs")


def test_load_is_stable_across_calls(tmp_path: Path):
    store = ConfigStore(base_dir=tmp_path)
    first = store.load()
    second = ConfigStore(base_dir=tmp_path).load()
    assert first.api_key == second.api_key
    assert first.admin_password == second.admin_password


def test_save_then_load_roundtrip(tmp_path: Path):
    store = ConfigStore(base_dir=tmp_path)
    cfg = store.load()
    cfg.port = 9123
    store.save(cfg)
    assert ConfigStore(base_dir=tmp_path).load().port == 9123
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_config.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'mflux_server.storage.config'`

- [ ] **Step 3: 写实现**

`src/mflux_server/storage/__init__.py`：（空文件）

`src/mflux_server/storage/config.py`：
```python
import json
import secrets
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_BASE = Path.home() / ".mflux-server"


@dataclass
class Config:
    api_key: str
    admin_password: str
    output_dir: str
    host: str = "127.0.0.1"
    port: int = 8000
    default_model: str = "z-image-turbo"
    default_steps: int = 9


class ConfigStore:
    def __init__(self, base_dir: Path = DEFAULT_BASE):
        self.base_dir = Path(base_dir)
        self.path = self.base_dir / "config.json"

    def load(self) -> Config:
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return Config(**data)
        cfg = Config(
            api_key="sk-" + secrets.token_hex(24),
            admin_password=secrets.token_hex(8),
            output_dir=str(self.base_dir / "outputs"),
        )
        self.save(cfg)
        return cfg

    def save(self, cfg: Config) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_config.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add src/mflux_server/storage/__init__.py src/mflux_server/storage/config.py tests/test_config.py
git commit -m "feat: file-based config store with auto-generated api key"
```

---

## Task 3: 历史存储（HistoryStore）

**Files:**
- Create: `src/mflux_server/storage/history.py`
- Test: `tests/test_history.py`

- [ ] **Step 1: 写失败的测试**

`tests/test_history.py`：
```python
from pathlib import Path
from mflux_server.storage.history import HistoryStore

PNG = b"\x89PNG\r\n\x1a\n-fake-bytes"


def test_save_writes_png_and_metadata(tmp_path: Path):
    store = HistoryStore(output_dir=tmp_path)
    entry = store.save(PNG, prompt="a cat", model="z-image-turbo", params={"seed": 1})
    assert (tmp_path / f"{entry.id}.png").read_bytes() == PNG
    assert (tmp_path / f"{entry.id}.json").exists()
    assert entry.prompt == "a cat"
    assert entry.model == "z-image-turbo"


def test_get_returns_saved_entry(tmp_path: Path):
    store = HistoryStore(output_dir=tmp_path)
    entry = store.save(PNG, prompt="p", model="m", params={})
    loaded = store.get(entry.id)
    assert loaded is not None
    assert loaded.prompt == "p"
    assert store.get("nonexistent") is None


def test_list_sorted_newest_first(tmp_path: Path):
    store = HistoryStore(output_dir=tmp_path)
    a = store.save(PNG, prompt="a", model="m", params={}, created_at=100.0)
    b = store.save(PNG, prompt="b", model="m", params={}, created_at=200.0)
    ids = [e.id for e in store.list()]
    assert ids == [b.id, a.id]


def test_delete_removes_files(tmp_path: Path):
    store = HistoryStore(output_dir=tmp_path)
    entry = store.save(PNG, prompt="p", model="m", params={})
    assert store.delete(entry.id) is True
    assert not (tmp_path / f"{entry.id}.png").exists()
    assert store.delete(entry.id) is False
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_history.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'mflux_server.storage.history'`

- [ ] **Step 3: 写实现**

`src/mflux_server/storage/history.py`：
```python
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class HistoryEntry:
    id: str
    prompt: str
    model: str
    params: dict
    created_at: float


class HistoryStore:
    def __init__(self, output_dir):
        self.output_dir = Path(output_dir)

    def save(self, image_bytes: bytes, prompt: str, model: str,
             params: dict, created_at: Optional[float] = None) -> HistoryEntry:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        entry = HistoryEntry(
            id=uuid.uuid4().hex,
            prompt=prompt,
            model=model,
            params=params,
            created_at=created_at if created_at is not None else time.time(),
        )
        (self.output_dir / f"{entry.id}.png").write_bytes(image_bytes)
        (self.output_dir / f"{entry.id}.json").write_text(
            json.dumps(asdict(entry), indent=2), encoding="utf-8"
        )
        return entry

    def image_path(self, entry_id: str) -> Path:
        return self.output_dir / f"{entry_id}.png"

    def get(self, entry_id: str) -> Optional[HistoryEntry]:
        meta = self.output_dir / f"{entry_id}.json"
        if not meta.exists():
            return None
        return HistoryEntry(**json.loads(meta.read_text(encoding="utf-8")))

    def list(self) -> list:
        if not self.output_dir.exists():
            return []
        entries = []
        for meta in self.output_dir.glob("*.json"):
            entries.append(HistoryEntry(**json.loads(meta.read_text(encoding="utf-8"))))
        return sorted(entries, key=lambda e: e.created_at, reverse=True)

    def delete(self, entry_id: str) -> bool:
        png = self.output_dir / f"{entry_id}.png"
        meta = self.output_dir / f"{entry_id}.json"
        if not meta.exists():
            return False
        png.unlink(missing_ok=True)
        meta.unlink(missing_ok=True)
        return True
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_history.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: Commit**

```bash
git add src/mflux_server/storage/history.py tests/test_history.py
git commit -m "feat: file-based history store (png + json metadata)"
```

---

## Task 4: 引擎抽象 + 注册表

**Files:**
- Create: `src/mflux_server/engines/__init__.py`（空）
- Create: `src/mflux_server/engines/base.py`
- Create: `src/mflux_server/engines/registry.py`
- Create: `tests/fakes.py`
- Test: `tests/test_engine_registry.py`

- [ ] **Step 1: 写 fakes + 失败的测试**

`tests/fakes.py`：
```python
import base64
from mflux_server.engines.base import BaseEngine, ModelInfo, GenerationRequest

# 最小合法的 1x1 PNG，用于在不跑真实模型的情况下测试
ONE_PX_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+M8AAAMBAQDJ/aPjAAAAAElFTkSuQmCC"
)


class FakeEngine(BaseEngine):
    id = "fake"

    def __init__(self, model_name="fake-model"):
        self.model_name = model_name
        self.calls = []

    def models(self):
        return [ModelInfo(name=self.model_name, family="fake",
                          engine=self.id, capabilities=["text-to-image"])]

    def generate(self, req: GenerationRequest):
        self.calls.append(req)
        return [ONE_PX_PNG for _ in range(req.n)]
```

`tests/test_engine_registry.py`：
```python
import pytest
from mflux_server.engines.registry import EngineRegistry
from tests.fakes import FakeEngine


def test_models_aggregates_across_engines():
    reg = EngineRegistry()
    reg.register(FakeEngine(model_name="m1"))
    names = [m.name for m in reg.models()]
    assert "m1" in names


def test_find_model_and_engine_for():
    reg = EngineRegistry()
    engine = FakeEngine(model_name="m1")
    reg.register(engine)
    assert reg.find_model("m1").name == "m1"
    assert reg.find_model("missing") is None
    assert reg.engine_for("m1") is engine


def test_engine_for_unknown_raises():
    reg = EngineRegistry()
    with pytest.raises(KeyError):
        reg.engine_for("missing")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_engine_registry.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'mflux_server.engines.base'`

- [ ] **Step 3: 写实现**

`src/mflux_server/engines/__init__.py`：（空文件）

`src/mflux_server/engines/base.py`：
```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


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


@dataclass
class ModelInfo:
    name: str
    family: str
    engine: str
    capabilities: list


class BaseEngine(ABC):
    id: str = "base"

    @abstractmethod
    def models(self) -> list:
        """返回该引擎支持的 ModelInfo 列表。"""

    @abstractmethod
    def generate(self, req: GenerationRequest) -> list:
        """同步执行生成，返回 PNG 字节列表（长度 == req.n）。"""
```

`src/mflux_server/engines/registry.py`：
```python
from typing import Optional
from mflux_server.engines.base import BaseEngine, ModelInfo


class EngineRegistry:
    def __init__(self):
        self._engines = {}          # engine_id -> BaseEngine
        self._model_index = {}      # model_name -> engine_id

    def register(self, engine: BaseEngine) -> None:
        self._engines[engine.id] = engine
        for info in engine.models():
            self._model_index[info.name] = engine.id

    def models(self) -> list:
        out = []
        for engine in self._engines.values():
            out.extend(engine.models())
        return out

    def find_model(self, name: str) -> Optional[ModelInfo]:
        for info in self.models():
            if info.name == name:
                return info
        return None

    def engine_for(self, model_name: str) -> BaseEngine:
        return self._engines[self._model_index[model_name]]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_engine_registry.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add src/mflux_server/engines/__init__.py src/mflux_server/engines/base.py src/mflux_server/engines/registry.py tests/fakes.py tests/test_engine_registry.py
git commit -m "feat: engine abstraction (BaseEngine) and registry"
```

---

## Task 5: 任务队列（单 worker 串行）

**Files:**
- Create: `src/mflux_server/queue.py`
- Test: `tests/test_queue.py`

- [ ] **Step 1: 写失败的测试**

`tests/test_queue.py`：
```python
import threading
import time
from mflux_server.queue import JobQueue
from mflux_server.engines.base import GenerationRequest
from mflux_server.engines.registry import EngineRegistry
from tests.fakes import FakeEngine, ONE_PX_PNG


def _registry():
    reg = EngineRegistry()
    reg.register(FakeEngine(model_name="fake-model"))
    return reg


def test_submit_and_wait_returns_result():
    q = JobQueue(_registry())
    q.start()
    job = q.submit(GenerationRequest(model="fake-model", prompt="hi", n=2))
    q.wait(job, timeout=5)
    assert job.status == "done"
    assert job.result == [ONE_PX_PNG, ONE_PX_PNG]


def test_unknown_model_marks_job_error():
    q = JobQueue(_registry())
    q.start()
    job = q.submit(GenerationRequest(model="nope", prompt="hi"))
    q.wait(job, timeout=5)
    assert job.status == "error"
    assert job.error


def test_jobs_run_serially_in_submit_order():
    order = []

    class SlowEngine(FakeEngine):
        def generate(self, req):
            order.append(req.prompt)
            time.sleep(0.05)
            return super().generate(req)

    reg = EngineRegistry()
    reg.register(SlowEngine(model_name="fake-model"))
    q = JobQueue(reg)
    q.start()
    jobs = [q.submit(GenerationRequest(model="fake-model", prompt=str(i))) for i in range(3)]
    for j in jobs:
        q.wait(j, timeout=5)
    assert order == ["0", "1", "2"]


def test_get_and_list():
    q = JobQueue(_registry())
    q.start()
    job = q.submit(GenerationRequest(model="fake-model", prompt="hi"))
    q.wait(job, timeout=5)
    assert q.get(job.id) is job
    assert job in q.list()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_queue.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'mflux_server.queue'`

- [ ] **Step 3: 写实现**

`src/mflux_server/queue.py`：
```python
import queue as _queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from mflux_server.engines.base import GenerationRequest
from mflux_server.engines.registry import EngineRegistry


@dataclass
class Job:
    id: str
    request: GenerationRequest
    status: str = "queued"           # queued | running | done | error
    result: Optional[list] = None    # list[bytes]
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    done: threading.Event = field(default_factory=threading.Event)


class JobQueue:
    def __init__(self, registry: EngineRegistry):
        self._registry = registry
        self._q: "_queue.Queue[Job]" = _queue.Queue()
        self._jobs = {}
        self._lock = threading.Lock()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._started = False

    def start(self) -> None:
        if not self._started:
            self._started = True
            self._worker.start()

    def submit(self, req: GenerationRequest) -> Job:
        job = Job(id=uuid.uuid4().hex, request=req)
        with self._lock:
            self._jobs[job.id] = job
        self._q.put(job)
        return job

    def wait(self, job: Job, timeout: Optional[float] = None) -> Job:
        job.done.wait(timeout)
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    def _run(self) -> None:
        while True:
            job = self._q.get()
            job.status = "running"
            try:
                engine = self._registry.engine_for(job.request.model)
                job.result = engine.generate(job.request)
                job.status = "done"
            except Exception as exc:  # noqa: BLE001 - 队列 worker 必须吞掉异常
                job.error = str(exc) or exc.__class__.__name__
                job.status = "error"
            finally:
                job.done.set()
                self._q.task_done()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_queue.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: Commit**

```bash
git add src/mflux_server/queue.py tests/test_queue.py
git commit -m "feat: in-memory single-worker job queue"
```

---

## Task 6: mflux 图像引擎（懒加载）

**Files:**
- Create: `src/mflux_server/engines/mflux_image.py`
- Test: `tests/test_mflux_engine.py`

说明：mflux 仅在 Apple Silicon 可装，所以本文件**不能在模块顶层 import mflux**——只在 `generate()` 内部懒加载。单元测试只验证模型表和 import 安全性，不跑真实生成（真实生成放 Task 10 的手动冒烟测试）。

- [ ] **Step 1: 写失败的测试**

`tests/test_mflux_engine.py`：
```python
from mflux_server.engines.mflux_image import MfluxImageEngine


def test_import_does_not_require_mflux():
    # 仅构造引擎、读模型表，不应触发 mflux 导入
    engine = MfluxImageEngine()
    names = [m.name for m in engine.models()]
    assert "z-image-turbo" in names


def test_models_are_text_to_image():
    engine = MfluxImageEngine()
    for info in engine.models():
        assert "text-to-image" in info.capabilities
        assert info.engine == "mflux-image"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_mflux_engine.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'mflux_server.engines.mflux_image'`

- [ ] **Step 3: 写实现**

`src/mflux_server/engines/mflux_image.py`：
```python
import os
import random
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from mflux_server.engines.base import BaseEngine, GenerationRequest, ModelInfo


@dataclass
class _ModelSpec:
    name: str
    family: str
    default_steps: int
    # loader(quantize) -> mflux 模型实例。懒加载：函数体内才 import mflux。
    loader: Callable


def _load_z_image_turbo(quantize):
    from mflux.models.z_image import ZImageTurbo  # 懒加载，仅 macOS 可用
    return ZImageTurbo(quantize=quantize) if quantize else ZImageTurbo()


# 当前支持的模型表。新增模型 = 在此处加一行 _ModelSpec（机制已完整，无需改其他代码）。
_SPECS = {
    "z-image-turbo": _ModelSpec(
        name="z-image-turbo", family="z-image", default_steps=9,
        loader=_load_z_image_turbo,
    ),
}


class MfluxImageEngine(BaseEngine):
    id = "mflux-image"

    def __init__(self):
        self._loaded = {}   # (model_name, quantize) -> mflux 模型实例

    def models(self) -> list:
        return [
            ModelInfo(name=s.name, family=s.family, engine=self.id,
                      capabilities=["text-to-image"])
            for s in _SPECS.values()
        ]

    def _get_model(self, model_name: str, quantize):
        key = (model_name, quantize)
        if key not in self._loaded:
            # 内存有限：加载新模型前清掉旧的
            self._loaded.clear()
            self._loaded[key] = _SPECS[model_name].loader(quantize)
        return self._loaded[key]

    def generate(self, req: GenerationRequest) -> list:
        spec = _SPECS[req.model]
        model = self._get_model(req.model, req.quantize)
        steps = req.steps if req.steps is not None else spec.default_steps
        images = []
        for i in range(req.n):
            seed = req.seed + i if req.seed is not None else random.randint(0, 2**31 - 1)
            generated = model.generate_image(
                prompt=req.prompt,
                seed=seed,
                num_inference_steps=steps,
                width=req.width,
                height=req.height,
            )
            images.append(self._to_png_bytes(generated))
        return images

    @staticmethod
    def _to_png_bytes(generated) -> bytes:
        # mflux 返回对象保证有 .save(path)；用临时文件取 PNG 字节，避免耦合其内部类型
        fd, tmp = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            generated.save(tmp)
            return Path(tmp).read_bytes()
        finally:
            os.unlink(tmp)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_mflux_engine.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add src/mflux_server/engines/mflux_image.py tests/test_mflux_engine.py
git commit -m "feat: mflux image engine with lazy model loading"
```

---

## Task 7: 鉴权依赖

**Files:**
- Create: `src/mflux_server/api/__init__.py`（空）
- Create: `src/mflux_server/api/auth.py`

（鉴权行为在 Task 8 的 API 测试里一起验证，因为它依赖 FastAPI 请求上下文。）

- [ ] **Step 1: 写实现**

`src/mflux_server/api/__init__.py`：（空文件）

`src/mflux_server/api/auth.py`：
```python
from fastapi import Header, HTTPException, Request
from typing import Optional


def require_api_key(request: Request, authorization: Optional[str] = Header(None)) -> None:
    expected = request.app.state.config.api_key
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer API key")
    if authorization[len("Bearer "):] != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")
```

- [ ] **Step 2: Commit**

```bash
git add src/mflux_server/api/__init__.py src/mflux_server/api/auth.py
git commit -m "feat: bearer api key auth dependency"
```

---

## Task 8: OpenAI 路由 + 文件服务 + 应用装配

**Files:**
- Create: `src/mflux_server/api/openai.py`
- Create: `src/mflux_server/api/files.py`
- Create: `src/mflux_server/app.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: 写失败的测试**

`tests/test_api.py`：
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
    app = create_app(config=config, registry=registry,
                     job_queue=job_queue, history=history)
    with TestClient(app) as c:
        c.api_key = config.api_key
        yield c


def _auth(client):
    return {"Authorization": f"Bearer {client.api_key}"}


def test_generations_requires_api_key(client):
    r = client.post("/v1/images/generations", json={"prompt": "hi", "model": "fake-model"})
    assert r.status_code == 401
    assert r.json()["error"]["type"]


def test_generations_returns_b64(client):
    r = client.post("/v1/images/generations",
                    headers=_auth(client),
                    json={"prompt": "hi", "model": "fake-model", "n": 2})
    assert r.status_code == 200
    body = r.json()
    assert len(body["data"]) == 2
    assert base64.b64decode(body["data"][0]["b64_json"]) == ONE_PX_PNG


def test_generations_url_format_serves_file(client):
    r = client.post("/v1/images/generations",
                    headers=_auth(client),
                    json={"prompt": "hi", "model": "fake-model",
                          "response_format": "url"})
    url = r.json()["data"][0]["url"]
    path = url[url.index("/files/"):]
    img = client.get(path)
    assert img.status_code == 200
    assert img.content == ONE_PX_PNG


def test_unknown_model_returns_404_openai_error(client):
    r = client.post("/v1/images/generations",
                    headers=_auth(client),
                    json={"prompt": "hi", "model": "ghost"})
    assert r.status_code == 404
    assert r.json()["error"]["message"]


def test_size_parsing_passes_dimensions(client):
    r = client.post("/v1/images/generations",
                    headers=_auth(client),
                    json={"prompt": "hi", "model": "fake-model", "size": "512x768"})
    assert r.status_code == 200
    req = client.app.state.registry.engine_for("fake-model").calls[-1]
    assert (req.width, req.height) == (512, 768)


def test_list_models(client):
    r = client.get("/v1/models", headers=_auth(client))
    assert r.status_code == 200
    ids = [m["id"] for m in r.json()["data"]]
    assert "fake-model" in ids
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_api.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'mflux_server.app'`

- [ ] **Step 3: 写文件服务路由**

`src/mflux_server/api/files.py`：
```python
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

router = APIRouter()


@router.get("/files/{entry_id}.png")
def get_file(entry_id: str, request: Request):
    path = request.app.state.history.image_path(entry_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(path, media_type="image/png")
```

- [ ] **Step 4: 写 OpenAI 路由**

`src/mflux_server/api/openai.py`：
```python
import base64
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from mflux_server.api.auth import require_api_key
from mflux_server.engines.base import GenerationRequest

router = APIRouter()


class GenerationsBody(BaseModel):
    prompt: str
    model: Optional[str] = None
    n: int = 1
    size: str = "1024x1024"
    response_format: str = "b64_json"
    steps: Optional[int] = None
    guidance: Optional[float] = None
    seed: Optional[int] = None
    lora: list = []
    quantize: Optional[int] = None


def _parse_size(size: str):
    try:
        w, h = size.lower().split("x")
        return int(w), int(h)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail=f"Invalid size: {size!r}")


@router.post("/v1/images/generations", dependencies=[Depends(require_api_key)])
def generations(body: GenerationsBody, request: Request):
    state = request.app.state
    model_name = body.model or state.config.default_model
    if state.registry.find_model(model_name) is None:
        raise HTTPException(status_code=404, detail=f"Model not found: {model_name}")

    width, height = _parse_size(body.size)
    gen_req = GenerationRequest(
        model=model_name, prompt=body.prompt, n=body.n,
        width=width, height=height, steps=body.steps,
        guidance=body.guidance, seed=body.seed,
        lora=body.lora, quantize=body.quantize,
    )
    job = state.queue.submit(gen_req)
    state.queue.wait(job, timeout=600)
    if job.status != "done":
        raise HTTPException(status_code=500, detail=job.error or "Generation timed out")

    params = {"steps": body.steps, "guidance": body.guidance,
              "seed": body.seed, "size": body.size}
    data = []
    for image_bytes in job.result:
        entry = state.history.save(image_bytes, prompt=body.prompt,
                                   model=model_name, params=params)
        if body.response_format == "url":
            base = str(request.base_url).rstrip("/")
            data.append({"url": f"{base}/files/{entry.id}.png"})
        else:
            data.append({"b64_json": base64.b64encode(image_bytes).decode()})
    return {"created": int(time.time()), "data": data}


@router.get("/v1/models", dependencies=[Depends(require_api_key)])
def list_models(request: Request):
    models = request.app.state.registry.models()
    return {
        "object": "list",
        "data": [
            {"id": m.name, "object": "model", "owned_by": m.engine}
            for m in models
        ],
    }
```

- [ ] **Step 5: 写应用装配**

`src/mflux_server/app.py`：
```python
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from mflux_server.api import files, openai


def create_app(config, registry, job_queue, history) -> FastAPI:
    app = FastAPI(title="mflux-server")
    app.state.config = config
    app.state.registry = registry
    app.state.queue = job_queue
    app.state.history = history

    @app.on_event("startup")
    def _start_worker():
        job_queue.start()

    @app.exception_handler(HTTPException)
    def _openai_error(request, exc: HTTPException):
        code_map = {400: "invalid_request_error", 401: "authentication_error",
                    404: "invalid_request_error", 500: "server_error"}
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {
                "message": exc.detail,
                "type": code_map.get(exc.status_code, "server_error"),
                "code": exc.status_code,
            }},
        )

    app.include_router(openai.router)
    app.include_router(files.router)
    return app
```

- [ ] **Step 6: 跑测试确认通过**

Run: `pytest tests/test_api.py -v`
Expected: PASS（6 passed）

- [ ] **Step 7: Commit**

```bash
git add src/mflux_server/api/openai.py src/mflux_server/api/files.py src/mflux_server/app.py tests/test_api.py
git commit -m "feat: OpenAI-compatible generations + models routes, app assembly"
```

---

## Task 9: CLI 启动命令

**Files:**
- Create: `src/mflux_server/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: 写失败的测试**

`tests/test_cli.py`：
```python
from mflux_server.cli import build_app_from_config


def test_build_app_from_config_wires_everything(tmp_path, monkeypatch):
    monkeypatch.setenv("MFLUX_SERVER_HOME", str(tmp_path))
    app = build_app_from_config()
    assert app.state.config.api_key.startswith("sk-")
    # mflux 引擎已注册
    assert app.state.registry.find_model("z-image-turbo") is not None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL，`ImportError: cannot import name 'build_app_from_config'`

- [ ] **Step 3: 写实现**

`src/mflux_server/cli.py`：
```python
import argparse
import os
from pathlib import Path

from mflux_server.app import create_app
from mflux_server.engines.mflux_image import MfluxImageEngine
from mflux_server.engines.registry import EngineRegistry
from mflux_server.queue import JobQueue
from mflux_server.storage.config import DEFAULT_BASE, ConfigStore
from mflux_server.storage.history import HistoryStore


def build_app_from_config():
    base = Path(os.environ.get("MFLUX_SERVER_HOME", str(DEFAULT_BASE)))
    config = ConfigStore(base_dir=base).load()
    registry = EngineRegistry()
    registry.register(MfluxImageEngine())
    job_queue = JobQueue(registry)
    history = HistoryStore(output_dir=config.output_dir)
    return create_app(config=config, registry=registry,
                      job_queue=job_queue, history=history)


def main():
    parser = argparse.ArgumentParser(prog="mflux-server")
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start", help="Start the server")
    start.add_argument("--host", default=None)
    start.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    if args.command == "start":
        import uvicorn
        app = build_app_from_config()
        host = args.host or app.state.config.host
        port = args.port or app.state.config.port
        print(f"mflux-server on http://{host}:{port}")
        print(f"API key: {app.state.config.api_key}")
        print(f"Admin password: {app.state.config.admin_password}")
        uvicorn.run(app, host=host, port=port)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_cli.py -v`
Expected: PASS（1 passed）

- [ ] **Step 5: 跑全量测试**

Run: `pytest -q`
Expected: 全部 PASS（约 20 passed）

- [ ] **Step 6: Commit**

```bash
git add src/mflux_server/cli.py tests/test_cli.py
git commit -m "feat: cli start command wiring mflux engine"
```

---

## Task 10: 真实模型冒烟测试（手动，仅 Apple Silicon）

**Files:** 无新代码，文档化手动验证步骤。

不进 CI（会下载数 GB 权重、耗时分钟级）。在一台 Apple Silicon Mac 上手动执行：

- [ ] **Step 1: 安装含 mflux 的依赖**

Run: `pip install -e ".[mflux,dev]"`
Expected: mflux 安装成功（仅 Apple Silicon）

- [ ] **Step 2: 启动服务**

Run: `mflux-server start`
Expected: 打印 `http://127.0.0.1:8000`、API key、admin password；首次会在 `~/.mflux-server/` 生成 config.json

- [ ] **Step 3: 用 OpenAI 风格请求验证文生图**

Run（替换 `<KEY>` 为上一步打印的 key）:
```bash
curl -s http://127.0.0.1:8000/v1/images/generations \
  -H "Authorization: Bearer <KEY>" \
  -H "Content-Type: application/json" \
  -d '{"model":"z-image-turbo","prompt":"a puffin on a cliff","size":"512x512"}' \
  | python -c "import sys,json,base64; d=json.load(sys.stdin); open('out.png','wb').write(base64.b64decode(d['data'][0]['b64_json'])); print('saved out.png')"
```
Expected: 生成 `out.png`，是一张可打开的图片；`~/.mflux-server/outputs/` 下出现对应的 png+json

- [ ] **Step 4: 验证官方 OpenAI SDK 兼容**

Run:
```bash
python -c "
from openai import OpenAI
c = OpenAI(base_url='http://127.0.0.1:8000/v1', api_key='<KEY>')
r = c.images.generate(model='z-image-turbo', prompt='a red apple', size='512x512')
print('ok', len(r.data))
"
```
Expected: 打印 `ok 1`，无异常

---

## Self-Review（plan 对 spec 的覆盖核对）

- ✅ OpenAI 文生图 `/v1/images/generations` → Task 8
- ✅ `/v1/models` → Task 8
- ✅ Bearer 鉴权（来自 config 的 key）→ Task 7 + Task 8 测试
- ✅ mflux 扩展参数（steps/guidance/seed/lora/quantize）→ Task 6 + Task 8 body 模型
- ✅ OpenAI 风格响应（b64_json / url）+ 文件服务 → Task 8
- ✅ OpenAI 风格错误体 → Task 8 异常处理器
- ✅ 单 worker 串行队列、阻塞等待 → Task 5 + Task 8
- ✅ 引擎抽象 + 注册表（视频扩展点）→ Task 4
- ✅ 文件存储 config.json + outputs/ → Task 2 + Task 3
- ✅ CLI 一条命令启动、首次生成 key → Task 9
- ✅ 测试不跑真实模型（FakeEngine）+ 手动冒烟 → Task 5/8 + Task 10

**本期不含**（在 Plan 2）：`/v1/images/edits`（图生图/Fill）、模型下载/加载管理、`/admin` 面板四页。`size` 参数仅做 `WxH` 解析（OpenAI 的命名尺寸如 `"1024x1024"` 已是该格式）。
```
