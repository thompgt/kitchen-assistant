import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .auth import WS_SUBPROTOCOL, auth_enabled, token_from_subprotocols, verify_token
from .live.gateway import LiveGateway
from .services.recipe_store import RecipeStore
from .services.timer_engine import TimerEngine
from .state_manager import state_manager
from .tools.registry import ToolRegistry

load_dotenv()

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Kitchen Assistant API",
    description="Real-time voice agent for high-noise kitchen environments",
    version="0.1.0",
)

timer_engine = TimerEngine(state_manager)
recipe_store = RecipeStore()
tool_registry = ToolRegistry(state_manager, timer_engine=timer_engine, recipe_store=recipe_store)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

HUD_DIST_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if HUD_DIST_DIR.is_dir():
    app.mount("/hud", StaticFiles(directory=HUD_DIST_DIR, html=True), name="hud")

# Env-driven origins. `allow_origins=["*"]` with `allow_credentials=True` is a
# combination browsers reject outright, so a wildcard here drops credentials
# rather than pretending; the default covers the app's own origin and the Vite
# dev server.
DEFAULT_ALLOWED_ORIGINS = (
    "http://localhost:8000,http://127.0.0.1:8000,"
    "http://localhost:5173,http://127.0.0.1:5173"
)
allowed_origins = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGINS).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials="*" not in allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.websocket("/ws/voice/{session_id}")
async def voice_websocket(websocket: WebSocket, session_id: str) -> None:
    # The token arrives as a subprotocol, never in the URL: query strings are
    # captured verbatim by proxies and access logs.
    token = token_from_subprotocols(websocket.scope.get("subprotocols"))
    await websocket.accept(subprotocol=WS_SUBPROTOCOL)
    if not verify_token(token):
        logger.warning("WebSocket rejected for session %s: invalid or missing token", session_id)
        await websocket.close(code=4001, reason="Invalid or missing token")
        return
    logger.info("WebSocket connected for session %s", session_id)
    # One gateway per connection: no shared conversation state across clients.
    gateway = LiveGateway(
        websocket=websocket,
        session_id=session_id,
        state_manager=state_manager,
        registry=tool_registry,
        timer_engine=timer_engine,
    )
    try:
        await gateway.run()
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for session %s", session_id)
    finally:
        logger.info("Session %s closed", session_id)


@app.get("/health")
async def health_check() -> dict:
    return {
        "status": "healthy",
        "redis_connected": state_manager.use_redis,
        "auth_enabled": auth_enabled(),
    }


@app.get("/")
async def root() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
