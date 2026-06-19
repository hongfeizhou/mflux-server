<!-- 语言 / Language: [English](README.md) · **简体中文** -->

# mflux-server

把 [mflux](https://github.com/filipstrand/mflux)（FLUX / Z-Image 等图像模型在 Apple MLX 上的移植）封装成一个 **OpenAI 风格的本地图像服务**，自带 **Web 管理面板**。可被官方 OpenAI SDK 直接调用，也可在浏览器里管理模型、查看历史、监控队列。

> **平台要求：macOS + Apple Silicon（M 系列芯片）。** 推理引擎基于 Apple MLX，仅能在 Apple Silicon 上运行。

---

## 示例

一条请求即可出图：

```bash
curl -s http://127.0.0.1:8000/v1/images/generations \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"z-image-turbo","prompt":"a red apple on a table","size":"768x768"}'
```

返回为 OpenAI 格式（`{ "data": [ { "b64_json": "..." } ] }`），把 base64 解码即得下面这张 PNG：

<p align="center"><img src="docs/assets/example-apple.png" width="384" alt="a red apple on a table"></p>

---

## 特性

- **OpenAI 兼容 API**
  - `POST /v1/images/generations` —— 文生图
  - `POST /v1/images/edits` —— 图生图（img2img）
  - `GET /v1/models` —— 模型列表
  - 响应/错误体遵循 OpenAI 格式，现有 OpenAI SDK / 客户端零改动接入
  - 支持 mflux 原生扩展参数：`steps` / `guidance` / `seed` / `negative_prompt` / `quantize` / 图生图 `strength`
- **Web 管理面板 `/admin`**
  - 登录（管理密码 + 签名 session）
  - 仪表盘：队列实时状态（HTMX 轮询）、运行/排队任务、历史计数
  - 模型管理：列出模型、下载（HuggingFace）、删除本地权重、设默认
  - 画廊 / 历史：网格浏览、重新生成、下载、删除
  - 设置：查看 / 重置 API Key、查看默认参数与监听地址
- **单 worker 串行队列** —— Apple Silicon 一次只跑一个模型，所有生成任务串行执行
- **纯文件存储** —— 配置 `~/.mflux-server/config.json`，图片 + 元数据存在 `outputs/`，无数据库
- **可插拔引擎层** —— `BaseEngine` + 注册表，未来接视频/其它引擎只需注册一个新 engine，API 与面板无需改动
- **零 Node 构建** —— 面板用服务端渲染 + vendored HTMX + 手写 CSS，离线可用

---

## 安装

需要 Python ≥ 3.10（mflux 要求）。推荐用 Homebrew 的 Python：

```bash
git clone https://github.com/hongfeizhou/mflux-server.git
cd mflux-server
python3.11 -m venv .venv
.venv/bin/python -m pip install -e ".[mflux]"
```

`mflux` 是可选依赖（`[mflux]` extra），仅在 Apple Silicon 可装。只想跑测试 / 开发不出图，可只装核心 + dev：`pip install -e ".[dev]"`。

---

## 快速开始

```bash
.venv/bin/mflux-server start          # 默认 127.0.0.1:8000
# 启动时会打印 API key 和 admin 密码，并写入 ~/.mflux-server/config.json
```

首次运行会自动生成 API Key 与管理密码。可用 `--host` / `--port` 覆盖。

### 用 OpenAI SDK 调用

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8000/v1", api_key="<你的-api-key>")

# 文生图
r = client.images.generate(model="z-image-turbo", prompt="a puffin on a cliff", size="1024x1024")
print(r.data[0].b64_json[:32])
```

### 用 curl

```bash
KEY=<你的-api-key>

# 文生图
curl -s http://127.0.0.1:8000/v1/images/generations \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"z-image-turbo","prompt":"a red apple","size":"512x512","seed":42}'

# 图生图（multipart）
curl -s http://127.0.0.1:8000/v1/images/edits \
  -H "Authorization: Bearer $KEY" \
  -F image=@source.png -F prompt="make it watercolor" \
  -F model=z-image-turbo -F strength=0.6 -F size=512x512
```

### 管理面板

浏览器打开 `http://127.0.0.1:8000/admin`，用启动时打印的 **admin 密码** 登录。

---

## API 参考

### `POST /v1/images/generations`

```jsonc
{
  "model": "z-image-turbo",        // 不传则用默认模型
  "prompt": "a cat astronaut",
  "n": 1,
  "size": "1024x1024",
  "response_format": "b64_json",   // 或 "url"（指向 /files/{id}.png）
  // mflux 扩展参数（可选）
  "steps": 9, "guidance": 3.5, "seed": 42, "quantize": 8
}
```

响应（OpenAI 格式）：`{ "created": <ts>, "data": [ { "b64_json": "..." } ] }`

### `POST /v1/images/edits`（multipart/form-data）

字段：`image`（必填，源图）、`prompt`（必填）、`model`、`n`、`size`、`response_format`、`steps`、`guidance`、`seed`、`strength`（图生图强度）、`negative_prompt`、`quantize`。

### `GET /v1/models`

返回 OpenAI models 列表格式。

### 鉴权

所有 `/v1/*` 需要 `Authorization: Bearer <api_key>`；`/admin/api/*` 接受 session cookie **或** Bearer key。

### 管理 API（`/admin/api/*`，需登录或 Bearer）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/admin/api/models` | 模型列表（含下载状态、大小、是否默认）|
| POST | `/admin/api/models/{name}/download` | 后台下载，返回 `job_id` |
| GET | `/admin/api/models/downloads/{job_id}` | 下载进度 |
| DELETE | `/admin/api/models/{name}` | 删除本地权重 |
| POST | `/admin/api/models/{name}/default` | 设为默认模型 |
| GET | `/admin/api/history` | 历史列表 |
| DELETE | `/admin/api/history/{id}` | 删除一条 |
| POST | `/admin/api/history/{id}/rerun` | 按原参数重新生成 |
| POST | `/admin/api/regenerate-key` | 重置 API Key |

---

## 架构

```
FastAPI 单进程 (默认 127.0.0.1:8000)
  /v1/*    OpenAI 兼容 API ──┐
  /admin   Web 面板 ─────────┤
                            ▼
                   [ 任务队列 (内存) ] 单 worker 串行
                            ▼
               [ 引擎注册表 EngineRegistry ]
                 ├─ MfluxImageEngine (现实现，z-image-turbo)
                 └─ (预留：视频/其它引擎)
                            ▼
                   [ 模型管理器 ] ← HuggingFace
                            ▼
         文件存储 ~/.mflux-server/
           config.json
           outputs/{id}.png + {id}.json
```

目录结构：

```
src/mflux_server/
  cli.py                 # mflux-server start
  app.py                 # FastAPI 装配
  api/openai.py          # /v1 路由 + 参数映射
  api/auth.py            # Bearer 鉴权
  api/files.py           # /files/{id}.png
  api/admin_models.py    # /admin/api/models*
  engines/base.py        # GenerationRequest / ModelInfo / BaseEngine
  engines/registry.py    # EngineRegistry
  engines/mflux_image.py # mflux 引擎（懒加载）
  queue.py               # 内存单 worker 队列
  models/manager.py      # 模型下载/删除/设默认
  admin/                 # 面板：auth / web / history_api / templates / static
  storage/config.py      # config.json
  storage/history.py     # outputs/ 读写
```

---

## 配置

`~/.mflux-server/config.json`（首次启动自动生成）：

| 字段 | 说明 |
|---|---|
| `api_key` | OpenAI 风格 Bearer key（也用作 session 签名密钥）|
| `admin_password` | 面板登录密码 |
| `host` / `port` | 监听地址 |
| `default_model` | 不传 model 时使用的模型 |
| `default_steps` | 默认推理步数 |
| `output_dir` | 图片 + 元数据输出目录 |

可用环境变量 `MFLUX_SERVER_HOME` 覆盖配置/输出根目录（默认 `~/.mflux-server`）。

---

## 扩展：新增模型 / 引擎

- **新增 mflux 模型**：在 `engines/mflux_image.py` 的 `_SPECS` 加一行 `_ModelSpec`（名称、repo_id、家族、默认步数、loader），机制已完整，其它代码无需改。
- **新增引擎（如视频）**：实现 `BaseEngine`（`models()` + `generate()`），在 `cli.build_app_from_config` 里 `registry.register(...)`。队列与 API 通过 `registry.engine_for(model)` 派发，无需改动。

---

## 开发与测试

```bash
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest -q
```

测试用 `FakeEngine` 和 mock 的 huggingface_hub，**不下载真实模型、不依赖 mflux**，因此可在任意平台（含 Windows / Linux）跑通；真实出图需在 Apple Silicon 上手动验证。

设计与实现计划见 `docs/superpowers/`（specs + plans）。

---

## 已知限制 / 后续

- 仅 macOS / Apple Silicon（mflux/MLX 限制）。
- 生成为同步阻塞 + 单 worker 串行，适合单机单用户；高并发非设计目标。
- 暂未内置视频引擎（架构已预留扩展位）。
- `@app.on_event` 待迁移到 FastAPI lifespan（当前有 deprecation 警告，不影响功能）。

---

## 致谢

- [mflux](https://github.com/filipstrand/mflux) —— FLUX / Z-Image 等模型的 Apple MLX 移植
- 写法参照 [jundot/omlx](https://github.com/jundot/omlx)（LLM 版的同类本地服务）
