# mflux OpenAI 风格服务 + Admin 面板 — 设计文档

**日期**: 2026-06-17
**状态**: 已确认，待生成实现计划

## 1. 目标与范围

把 [mflux](https://github.com/filipstrand/mflux)（FLUX 等图像模型的 Apple MLX 移植）封装为一个本地服务：

- 暴露 **OpenAI 兼容的图像生成 API**（文生图 + 图生图）
- 提供 **Web Admin 面板**（API Key 管理、模型管理、历史/画廊、队列监控）
- 写法参照 [jundot/omlx](https://github.com/jundot/omlx)（LLM 版的同类项目）

### 平台约束（重要）

- **仅 macOS（Apple Silicon）**。mflux 基于 Apple MLX，无法在 Windows/非 Apple-Silicon 上做推理。Windows 支持需求已与用户确认放弃。

### 明确不做（YAGNI）

- **视频生成**：mflux 不支持。引擎层做成可插拔、为视频预留接口，但本期不实现任何视频引擎。
- **SQLite / 数据库**：单机单用户，纯文件存储。
- **多用户 / SaaS / 计费 / 角色权限**：单用户、单（或少量）API Key。
- **SwiftUI 菜单栏 App**：以后再说，本期只做 Python 包 + Web 面板 + CLI。

## 2. 整体架构

```
FastAPI 单进程 (默认绑定 127.0.0.1:8000)
  /v1/*   OpenAI 兼容 API ──┐
  /admin  Web 面板 ─────────┤
                           ▼
                  [ 任务队列 (内存) ] 单 worker 串行执行
                           ▼
              [ 引擎注册表 EngineRegistry ]
                ├─ MfluxImageEngine (本期实现)
                └─ VideoEngine (仅预留接口)
                           ▼
                  [ 模型管理器 ] ← HuggingFace
                           ▼
        文件存储 ~/.mflux-server/
          config.json
          outputs/{id}.png + outputs/{id}.json
```

### 关键设计点

1. **单 worker 串行队列**：Apple Silicon 一次只跑一个大模型，所有生成任务进同一内存队列串行执行。OpenAI 端点提交任务后**阻塞等待结果**（保证官方 OpenAI SDK 可直接调用）；面板通过 **SSE** 实时显示队列与进度。
2. **引擎抽象层**：`BaseEngine` 接口（`generate()` / `capabilities()`）。本期只实现 `MfluxImageEngine`。将来视频引擎只需新增并注册一个引擎，API 与面板无需改动。
3. **模型管理器**：加载/卸载/下载/量化/设默认。内存有限，同时只常驻一个模型（LRU 卸载）。
4. **纯文件存储**：`config.json` 存 API Key 与设置；`outputs/` 下每次生成一个 `{id}.png` + `{id}.json`（提示词、参数、模型、时间戳），画廊与历史直接读该目录。无数据库。

## 3. OpenAI 兼容 API

### 3.1 文生图 `POST /v1/images/generations`

```jsonc
{
  "model": "flux.2",
  "prompt": "a cat astronaut",
  "n": 1,
  "size": "1024x1024",
  "response_format": "b64_json",   // 或 "url" → 指向面板托管的图片
  // mflux 原生扩展参数（可选）
  "steps": 4, "guidance": 3.5, "seed": 42,
  "lora": ["name@0.8"], "quantize": 8
}
```

### 3.2 图生图 / 重绘 `POST /v1/images/edits`（multipart/form-data）

- `image`（必填）、`mask`（可选 → 触发 Fill 重绘）、`prompt`
- 与文生图相同的扩展参数
- 映射到 mflux 的 img2img / Fill 能力

### 3.3 模型列表 `GET /v1/models`

返回可用模型，采用 OpenAI models 列表格式。

### 3.4 响应格式

严格遵循 OpenAI：
```jsonc
{ "created": 1718600000, "data": [ { "b64_json": "..." } ] }
```

### 3.5 鉴权

所有 `/v1/*` 需要 `Authorization: Bearer <api_key>`，key 来自 `config.json`。

### 3.6 错误

统一 OpenAI 风格错误体：
```jsonc
{ "error": { "message": "...", "type": "...", "code": "..." } }
```
覆盖：模型不存在、显存不足(OOM)、参数非法、队列超时。

## 4. Admin 面板 `/admin`

服务端渲染 + HTMX/Alpine + Tailwind（全部 vendored CDN，离线可用）。登录用 `config.json` 中的密码换 session cookie；默认仅绑定 `127.0.0.1`。

页面：

1. **仪表盘** — 当前运行任务 + 进度条（SSE）、排队列表、已加载模型、内存占用、今日生成数。
2. **模型管理** — 列出模型家族；下载（HuggingFace，带进度）/ 删除 / 加载 / 卸载 / 设默认 / 选量化等级。
3. **画廊/历史** — 网格展示 `outputs/`，点开看完整参数与提示词，可「重新生成」「下载」「删除」。
4. **API Key & 设置** — 查看/重置 API Key、输出目录、默认生成参数、host/port。

## 5. 模块结构

`pip install` 安装，命令 `mflux-server start/stop/...`。

```
mflux_server/
  cli.py             # 启停命令
  app.py             # FastAPI 装配
  api/openai.py      # /v1 路由 + 参数映射
  admin/             # /admin 路由 + 模板 + vendored 静态资源
  engines/base.py    # BaseEngine 接口
  engines/mflux_image.py
  engines/registry.py
  queue.py           # 内存队列 + 单 worker
  models/manager.py  # 加载/下载/量化
  storage/config.py  # config.json
  storage/history.py # outputs/ 读写
```

## 6. 错误处理

- 模型不存在 / 未下载 → 422 + OpenAI 错误体
- 显存不足(OOM) → 优雅捕获，提示降低 size/量化，500 + 错误体
- 参数非法 → 400 + 错误体
- 队列超时 / 满 → 503/超时 + 错误体
- HuggingFace 下载失败 → 面板内显示错误，可重试

## 7. 测试策略

**原则：CI 不跑真实模型**（太慢太重）。

- 单元测试（mock 引擎）覆盖：
  - OpenAI → mflux 参数映射
  - 队列串行执行顺序
  - history 读写（`outputs/` 的 png+json）
  - config 读写
  - 引擎注册表 / capabilities
  - 鉴权（Bearer key、面板 session）
- 可选冒烟测试：用最小最快模型真实生成一张图，手动/本地触发，不进 CI。

## 8. 验收标准

1. 用官方 OpenAI Python SDK 指向本服务，`images.generate(...)` 能返回图片。
2. `POST /v1/images/edits` 能对上传图做 img2img / Fill。
3. `/admin` 可登录，四个页面功能可用：看到队列实时进度、下载/加载模型、浏览历史画廊、查看/重置 API Key。
4. 新增一个 dummy 视频引擎并注册后，`GET /v1/models` 能列出它，且无需改动 API/面板代码（验证扩展点）。
5. 单元测试全绿。
