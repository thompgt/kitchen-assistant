# Kitchen Assistant - Engineering Guidelines

## Build & Run Commands
- Install dependencies: `pip install -r app/requirements.txt`
- Run FastAPI app: `uvicorn app.main:app --reload`
- Run Tests: `pytest`
- Notebooks: Execute cells in `notebooks/` using `app/venv_new`

## Technical Standards
- Language: Python 3.11+
- Async: Native `async/await` for STT, Orchestrator, and Tool Execution.
- Latency: Optimized for <800ms Glass-to-Glass.
- State: Pydantic schemas in `app/schemas.py`, session persistence in `app/state_manager.py`.
- Tooling: All cooking tools in `app/tools/cooking_tools.py` with full docstrings.
- Style: PEP 8 compliant, type hints mandatory, no suppressed exceptions.

## Persona
- Executive Sous-Chef: Concise, professional, efficiency-focused. No conversational filler.
