from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv

from .state_manager import state_manager
from .models import RecipeState

load_dotenv()

app = FastAPI(
    title="Kitchen Assistant API",
    description="Real-time voice agent for high-noise kitchen environments",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "redis_connected": state_manager.use_redis
    }

@app.get("/")
async def root():
    return {"message": "Welcome to the Kitchen Assistant API. Use /docs for API documentation."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
