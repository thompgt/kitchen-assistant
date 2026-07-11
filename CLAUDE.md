# Kitchen Assistant - Engineering Guidelines

Architecture, component contracts, and ADRs live in [`ARCHITECTURE.md`](ARCHITECTURE.md).
The phased roadmap is [`workplan.md`](workplan.md) — follow it, commit in small steps.

## Build & Run Commands
- Install dependencies: `poetry install`
- Run FastAPI app: `poetry run uvicorn app.main:app --reload`
- Run tests: `poetry run pytest`
- Config: copy `.env.example` to `.env` and fill in (never commit `.env`)

## Layout
- `app/main.py` — FastAPI app, WebSocket route
- `app/schemas.py` — all Pydantic models (single source; no other schema module)
- `app/state_manager.py` — session persistence (in-memory default, optional Redis)
- `app/live/gateway.py` — LiveGateway: browser WS ↔ Gemini Live proxy
- `app/tools/cooking_tools.py` — cooking tools with full docstrings
- `app/tools/registry.py` — FunctionDeclarations + server-side dispatch
- `scripts/` — RAG ingestion/search utilities; `notebooks/` — exploration only

## Technical Standards
- Language: Python 3.11+, Poetry-managed
- Async: Native `async/await` for the Live gateway, orchestration, and tool execution.
- Latency: Optimized for <800ms Glass-to-Glass (budget in ARCHITECTURE.md).
- State: Pydantic schemas in `app/schemas.py`, session persistence in `app/state_manager.py`.
- Tooling: All cooking tools in `app/tools/cooking_tools.py` with full docstrings.
- Style: PEP 8 compliant, type hints mandatory, no suppressed exceptions.

## Persona
- Executive Sous-Chef: Concise, professional, efficiency-focused. No conversational filler.
