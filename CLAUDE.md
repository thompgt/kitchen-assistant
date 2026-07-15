# Kitchen Assistant - Engineering Guidelines

Architecture, component contracts, and ADRs live in [`ARCHITECTURE.md`](ARCHITECTURE.md).
The phased roadmap is [`workplan.md`](workplan.md) — follow it, commit in small steps.

## Build & Run Commands
- Install dependencies: `poetry install`
- Run FastAPI app: `poetry run uvicorn app.main:app --reload`
- Run tests: `poetry run pytest`
- Config: copy `.env.example` to `.env` and fill in (never commit `.env`)
- React HUD (optional): `cd frontend && npm install && npm run build` — builds to
  `frontend/dist`, which FastAPI serves at `/hud` if present. `npm run dev` runs it
  standalone on Vite's dev server, proxying `/ws` and `/health` to `localhost:8000`.
  The vanilla client at `/` (`static/`) keeps working either way.
- Docker: `docker build -t kitchen-assistant .` / `docker compose up --build`
  (multi-stage: builds the HUD, then the Python runtime). Optional Redis via
  `docker compose --profile redis up`.

## Layout
- `app/main.py` — FastAPI app, WebSocket route
- `app/auth.py` — `APP_AUTH_TOKEN` shared-token gate for the WS route
- `app/schemas.py` — all Pydantic models (single source; no other schema module)
- `app/state_manager.py` — session persistence (in-memory default, optional Redis)
- `app/live/gateway.py` — LiveGateway: browser WS ↔ Gemini Live proxy
- `app/tools/cooking_tools.py` — cooking tools with full docstrings
- `app/tools/registry.py` — FunctionDeclarations + server-side dispatch
- `scripts/` — RAG ingestion/search utilities; `notebooks/` — exploration only
- `static/` — vanilla JS voice client, served at `/`
- `frontend/` — React/TS/Tailwind/Zustand HUD (Phase 7), served at `/hud` once built

## Technical Standards
- Language: Python 3.11+, Poetry-managed
- Async: Native `async/await` for the Live gateway, orchestration, and tool execution.
- Latency: Optimized for <800ms Glass-to-Glass (budget in ARCHITECTURE.md).
- State: Pydantic schemas in `app/schemas.py`, session persistence in `app/state_manager.py`.
- Tooling: All cooking tools in `app/tools/cooking_tools.py` with full docstrings.
- Style: PEP 8 compliant, type hints mandatory, no suppressed exceptions.

## Persona
- Executive Sous-Chef: Concise, professional, efficiency-focused. No conversational filler.
