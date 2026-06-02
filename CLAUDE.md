# CLAUDE.md Guidelines

## Build & Test Commands
- Install dependencies: `pip install -r requirements.txt`
- Run tests: `pytest`
- Run backend: `uvicorn backend.main:app --reload --port 8000`

## Code Style & Architecture
- Code style: PEP 8 compliant, strict type hinting (`typing` module).
- Async execution: Use `async/await` natively for all network and file I/O operations.
- Error handling: Never suppress exceptions; wrap WebSocket loops in try/except blocks with explicit logging.
- System Design: Keep logic decoupled. Core server routes belong in `backend/api/`, third-party microservices (Deepgram, Cartesia) in `backend/services/`.
