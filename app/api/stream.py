from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ..services.stt import DeepgramSTT
import asyncio

router = APIRouter()

@router.websocket("/api/v1/stream")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    async def stt_callback(transcript: str):
        # Forward transcript to Orchestrator (Phase 4)
        # For now, just send back to client for debug
        await websocket.send_json({"type": "transcript", "text": transcript})

    stt = DeepgramSTT(stt_callback)
    if not await stt.start():
        await websocket.close(code=1011)
        return

    try:
        while True:
            data = await websocket.receive_bytes()
            await stt.send_audio(data)
    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"Streaming Error: {e}")
    finally:
        await stt.stop()
