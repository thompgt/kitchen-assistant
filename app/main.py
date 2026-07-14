import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.websocket("/ws/voice/{session_id}")
async def voice_websocket(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
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
    }


@app.get("/")
async def root() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
