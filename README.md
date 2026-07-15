# 👨‍🍳 Kitchen Assistant: Executive Sous-Chef AI

A real-time, hands-free kitchen voice assistant built on **Gemini Live**, **FastAPI**, and **DuckDB**. Talk to it while your hands are full — it sets timers, scales recipes, converts units, and reads back cooking steps, all through a bi-directional audio WebSocket.

Full architecture, component contracts, and ADRs live in [`ARCHITECTURE.md`](ARCHITECTURE.md). The phased build log is [`workplan.md`](workplan.md).

---

## 🏗️ How it works

```
Browser (mic + speaker) <--WS: PCM16 audio + JSON events--> FastAPI (app/main.py)
                                                                 │
                                                          LiveGateway (app/live/gateway.py)
                                                                 │
                                                      Gemini Live session (native audio + tools)
                                                                 │
                                              ToolRegistry (app/tools/registry.py) dispatches to:
                                              cooking_tools · TimerEngine · RecipeStore (DuckDB RAG)
```

One `LiveGateway` instance per WebSocket connection proxies the browser directly to a Gemini Live session — no separate STT/TTS services. Session state (active recipe, step index, running timers) lives in `app/state_manager.py` and is pushed back to the client as `state.snapshot` events.

---

## ✨ Key Features

- **🎙️ Hands-Free Control**: Voice in, voice out, via Gemini Live's native audio — barge-in (interrupting mid-sentence) is supported.
- **⏱️ Multi-Timer Management**: Set, label, cancel, and list overlapping timers; expiry is announced proactively, unprompted.
- **⚖️ Dynamic Recipe Scaling & Unit Conversion**: "Double this recipe," F↔C, kg/lb, l/fl oz, etc.
- **🔎 Recipe Search (RAG)**: Semantic search over a DuckDB + vector-similarity recipe catalog (`gemini-embedding-001`); "find me a mushroom recipe" → load → step-by-step navigation.
- **📷 Camera Doneness Checks**: Share a camera and ask "is this done?" — frames stream to Gemini Live alongside audio.
- **🖥️ Two clients**: a dependency-free vanilla JS client (`static/`) and a React/TypeScript HUD (`frontend/`) with a live timer board, instruction card, and scaled ingredient checklist.

---

## 🚀 Getting Started

### Prerequisites
- Python 3.11+ and [Poetry](https://python-poetry.org/)
- A Google AI (Gemini) API key with Live API access
- Node.js 18+ (only needed if you want to build the React HUD)

### Backend setup
```bash
git clone https://github.com/thompgt/kitchen-assistant.git
cd kitchen-assistant

poetry install
cp .env.example .env   # add your GOOGLE_API_KEY

poetry run uvicorn app.main:app --reload
```

Open **http://localhost:8000/** for the vanilla client. Microphone access requires `localhost` or HTTPS.

### React HUD (optional)
```bash
cd frontend
npm install
npm run build          # builds to frontend/dist, served at /hud once the backend is running
```
Or run it standalone with hot reload: `npm run dev` (proxies `/ws` and `/health` to `localhost:8000`).

### Recipe catalog
The catalog ships pre-built in `data/recipes.db`. To rebuild it from source or add recipes, edit `data/recipes_seed.json` and run:
```bash
poetry run python scripts/ingest_recipes.py       # loads/validates the JSON catalog into DuckDB
poetry run python scripts/setup_vector_search.py  # batch-embeds any recipes missing a vector
```

### Tests & lint
```bash
poetry run pytest         # backend — fakes the Gemini Live backend, no API key needed
poetry run ruff check .
cd frontend && npm run lint && npm run build   # frontend typecheck + lint
```
CI (`.github/workflows/ci.yml`) runs all of the above on every push/PR.

### Auth (optional)
The app is open-access by default (fine for local/LAN use). To gate it before exposing it publicly, set `APP_AUTH_TOKEN` in `.env` and share the URL with the token attached: `https://host/?token=<value>`. Both clients forward it to the WebSocket automatically. This is a single shared secret, not a user-account system — proportionate to a single-deployment kitchen appliance. Concurrent users already get independent state via `session_id`, with no auth required for that.

### Deployment (Docker)
```bash
docker build -t kitchen-assistant .
docker run -p 8000:8000 --env-file .env kitchen-assistant
```
Or with Compose (mounts `data/` for editing the recipe catalog without a rebuild):
```bash
docker compose up --build
```
Redis is optional and only relevant if you run multiple replicas needing shared session state — bring it up with `docker compose --profile redis up` and set `USE_REDIS=true`, `REDIS_URL=redis://redis:6379` in `.env`. A single container is fine with the in-memory default.

---

## 📁 Layout

| Path | Purpose |
|---|---|
| `app/main.py` | FastAPI app, `/ws/voice/{session_id}` route |
| `app/auth.py` | `APP_AUTH_TOKEN` shared-token gate for the WS route |
| `app/live/gateway.py` | `LiveGateway` — browser WS ↔ Gemini Live proxy, one instance per connection |
| `app/tools/` | Cooking tools (`cooking_tools.py`) + Gemini `FunctionDeclaration`s and dispatch (`registry.py`) |
| `app/services/timer_engine.py` | Real asyncio countdown timers with expiry callbacks |
| `app/services/recipe_store.py` | DuckDB + vector search over the recipe catalog |
| `app/schemas.py` | All Pydantic models (single source of truth) |
| `app/state_manager.py` | Per-session state, in-memory by default, optional Redis |
| `static/` | Vanilla JS voice client, served at `/` |
| `frontend/` | React/TS/Tailwind/Zustand HUD, served at `/hud` once built |
| `scripts/` | Recipe ingestion, vector search setup, Live API smoke test |
| `data/recipes_seed.json` | Source-of-truth recipe catalog (JSON) |
| `notebooks/` | Exploration only — EDA, multimodal experiments, an end-to-end app demo |
| `tests/` | pytest suite — fakes the Live backend and DuckDB, no external calls |

---

## 🗺️ Roadmap

The full phased build — repo hygiene, state hardening, Live migration, browser clients, timers, RAG, tests/CI, the React HUD, camera doneness checks, and auth/deployment — is complete; see [`workplan.md`](workplan.md) for the full history.

---

## 🛠️ Tech Stack

- **LLM**: Google Gemini Live (native audio + function calling)
- **Backend**: FastAPI, async/await throughout
- **Database**: DuckDB (+ `vss` extension for vector search)
- **Frontend**: Vanilla JS client + a React/TypeScript/Tailwind/Zustand HUD
- **Package managers**: Poetry (backend), npm (frontend)
- **CI**: GitHub Actions — ruff, pytest, frontend build
- **Deployment**: Docker (multi-stage build), docker-compose, optional Redis

---

## 📜 License
MIT License. Created by [thompgt](https://github.com/thompgt).
