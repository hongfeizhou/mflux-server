<!-- Language: **English** · [简体中文](README.zh-CN.md) -->

# mflux-server

Wrap [mflux](https://github.com/filipstrand/mflux) (a port of FLUX / Z-Image and other image models to Apple MLX) into an **OpenAI-style local image service** with a built-in **web admin panel**. Call it directly with the official OpenAI SDK, or manage models, browse history, and monitor the queue from your browser.

> **Requires macOS on Apple Silicon (M-series).** The inference engine is built on Apple MLX and runs on Apple Silicon only.

---

## Features

- **OpenAI-compatible API**
  - `POST /v1/images/generations` — text-to-image
  - `POST /v1/images/edits` — image-to-image (img2img)
  - `GET /v1/models` — list models
  - OpenAI-shaped responses and errors, so existing OpenAI SDKs/clients work with zero changes
  - mflux-native extension params supported: `steps` / `guidance` / `seed` / `negative_prompt` / `quantize`, plus `strength` for img2img
- **Web admin panel at `/admin`**
  - Login (admin password + signed session)
  - Dashboard: live queue status (HTMX polling), running/queued jobs, history counts
  - Model management: list, download (from HuggingFace), delete local weights, set default
  - Gallery / history: grid browsing, re-generate, download, delete
  - Settings: view / regenerate the API key, view default params and bind address
- **Single-worker serial queue** — Apple Silicon runs one model at a time, so all generation jobs run serially
- **File-based storage** — config at `~/.mflux-server/config.json`, images + metadata under `outputs/`, no database
- **Pluggable engine layer** — `BaseEngine` + a registry; adding a video/other engine later only requires registering a new engine, with no changes to the API or panel
- **No Node build** — the panel is server-rendered with vendored HTMX + hand-written CSS, fully offline

---

## Installation

Requires Python ≥ 3.10 (mflux's requirement). Homebrew's Python is recommended:

```bash
git clone https://github.com/hongfeizhou/mflux-server.git
cd mflux-server
python3.11 -m venv .venv
.venv/bin/python -m pip install -e ".[mflux]"
```

`mflux` is an optional dependency (the `[mflux]` extra) and installs on Apple Silicon only. To just run tests / develop without generating images, install core + dev instead: `pip install -e ".[dev]"`.

---

## Quick start

```bash
.venv/bin/mflux-server start          # defaults to 127.0.0.1:8000
# On start it prints the API key and admin password, and writes ~/.mflux-server/config.json
```

The first run auto-generates an API key and admin password. Override the bind address with `--host` / `--port`.

### With the OpenAI SDK

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8000/v1", api_key="<your-api-key>")

# text-to-image
r = client.images.generate(model="z-image-turbo", prompt="a puffin on a cliff", size="1024x1024")
print(r.data[0].b64_json[:32])
```

### With curl

```bash
KEY=<your-api-key>

# text-to-image
curl -s http://127.0.0.1:8000/v1/images/generations \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"z-image-turbo","prompt":"a red apple","size":"512x512","seed":42}'

# image-to-image (multipart)
curl -s http://127.0.0.1:8000/v1/images/edits \
  -H "Authorization: Bearer $KEY" \
  -F image=@source.png -F prompt="make it watercolor" \
  -F model=z-image-turbo -F strength=0.6 -F size=512x512
```

### Admin panel

Open `http://127.0.0.1:8000/admin` and log in with the **admin password** printed at startup.

---

## API reference

### `POST /v1/images/generations`

```jsonc
{
  "model": "z-image-turbo",        // falls back to the default model if omitted
  "prompt": "a cat astronaut",
  "n": 1,
  "size": "1024x1024",
  "response_format": "b64_json",   // or "url" (points at /files/{id}.png)
  // mflux extension params (optional)
  "steps": 9, "guidance": 3.5, "seed": 42, "quantize": 8
}
```

Response (OpenAI format): `{ "created": <ts>, "data": [ { "b64_json": "..." } ] }`

### `POST /v1/images/edits` (multipart/form-data)

Fields: `image` (required, source image), `prompt` (required), `model`, `n`, `size`, `response_format`, `steps`, `guidance`, `seed`, `strength` (img2img strength), `negative_prompt`, `quantize`.

### `GET /v1/models`

Returns the OpenAI models-list format.

### Authentication

All `/v1/*` endpoints require `Authorization: Bearer <api_key>`. The `/admin/api/*` endpoints accept a session cookie **or** a Bearer key.

### Admin API (`/admin/api/*`, requires login or Bearer)

| Method | Path | Description |
|---|---|---|
| GET | `/admin/api/models` | Model list (with download state, size, default flag) |
| POST | `/admin/api/models/{name}/download` | Start a background download, returns `job_id` |
| GET | `/admin/api/models/downloads/{job_id}` | Download progress |
| DELETE | `/admin/api/models/{name}` | Delete local weights |
| POST | `/admin/api/models/{name}/default` | Set as the default model |
| GET | `/admin/api/history` | History list |
| DELETE | `/admin/api/history/{id}` | Delete one entry |
| POST | `/admin/api/history/{id}/rerun` | Re-generate with the original params |
| POST | `/admin/api/regenerate-key` | Rotate the API key |

---

## Architecture

```
Single FastAPI process (default 127.0.0.1:8000)
  /v1/*    OpenAI-compatible API ──┐
  /admin   Web panel ─────────────┤
                                  ▼
                    [ Job queue (in-memory) ] single worker, serial
                                  ▼
                  [ EngineRegistry ]
                    ├─ MfluxImageEngine (implemented: z-image-turbo)
                    └─ (reserved: video / other engines)
                                  ▼
                    [ Model manager ] ← HuggingFace
                                  ▼
         File storage ~/.mflux-server/
           config.json
           outputs/{id}.png + {id}.json
```

Directory layout:

```
src/mflux_server/
  cli.py                 # mflux-server start
  app.py                 # FastAPI assembly
  api/openai.py          # /v1 routes + param mapping
  api/auth.py            # Bearer auth
  api/files.py           # /files/{id}.png
  api/admin_models.py    # /admin/api/models*
  engines/base.py        # GenerationRequest / ModelInfo / BaseEngine
  engines/registry.py    # EngineRegistry
  engines/mflux_image.py # mflux engine (lazy-loaded)
  queue.py               # in-memory single-worker queue
  models/manager.py      # model download/delete/set-default
  admin/                 # panel: auth / web / history_api / templates / static
  storage/config.py      # config.json
  storage/history.py     # outputs/ read/write
```

---

## Configuration

`~/.mflux-server/config.json` (auto-generated on first start):

| Field | Description |
|---|---|
| `api_key` | OpenAI-style Bearer key (also used as the session signing secret) |
| `admin_password` | Panel login password |
| `host` / `port` | Bind address |
| `default_model` | Model used when `model` is omitted |
| `default_steps` | Default inference steps |
| `output_dir` | Output dir for images + metadata |

Set `MFLUX_SERVER_HOME` to override the config/output root (defaults to `~/.mflux-server`).

---

## Extending: adding models / engines

- **Add an mflux model**: append a `_ModelSpec` row to `_SPECS` in `engines/mflux_image.py` (name, repo_id, family, default steps, loader). The mechanism is complete; nothing else changes.
- **Add an engine (e.g. video)**: implement `BaseEngine` (`models()` + `generate()`) and `registry.register(...)` it in `cli.build_app_from_config`. The queue and API dispatch via `registry.engine_for(model)`, so they need no changes.

---

## Development & testing

```bash
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest -q
```

Tests use a `FakeEngine` and a mocked huggingface_hub, so they **download no real models and don't depend on mflux** — they run on any platform (including Windows / Linux). Real image generation must be verified manually on Apple Silicon.

Design docs and implementation plans live under `docs/superpowers/` (specs + plans).

---

## Known limitations / roadmap

- macOS / Apple Silicon only (mflux/MLX constraint).
- Generation is synchronous + single-worker serial — suited to single-machine, single-user use; high concurrency is not a design goal.
- No built-in video engine yet (the architecture reserves an extension point for it).
- `@app.on_event` should migrate to FastAPI lifespan (currently emits a deprecation warning; functionality is unaffected).

---

## Acknowledgements

- [mflux](https://github.com/filipstrand/mflux) — the Apple MLX port of FLUX / Z-Image and other models
- Patterned after [jundot/omlx](https://github.com/jundot/omlx) (a similar local service for LLMs)
