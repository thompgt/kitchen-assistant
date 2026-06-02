from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ..services.stt import DeepgramSTT
from ..services.tts import CartesiaTTS
from ..orchestrator import KitchenOrchestrator
import asyncio
import uuid

router = APIRouter()

@router.websocket("/api/v1/stream")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    session_id = str(uuid.uuid4())
    orchestrator = KitchenOrchestrator()
    tts = CartesiaTTS()

    async def stt_callback(transcript: str):
        # Forward transcript to Orchestrator
        text_stream = orchestrator.process_utterance(session_id, transcript)
        
        # Pipe LLM text tokens into TTS
        audio_stream = tts.stream_speech(text_stream)
        
        async for audio_chunk in audio_stream:
            await websocket.send_bytes(audio_chunk)

    stt = DeepgramSTT(stt_callback)
    if not await stt.start():
        await websocket.close(code=1011)
        return

    try:
        while True:
            data = await websocket.receive_bytes()
            await stt.send_audio(data)
    except WebSocketDisconnect:
        print(f"Client {session_id} disconnected")
    except Exception as e:
        print(f"Streaming Error: {e}")
    finally:
        await stt.stop()
