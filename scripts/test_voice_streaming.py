import asyncio
import websockets
import json

async def test_voice():
    uri = "ws://127.0.0.1:8000/ws/voice/test-session"
    async with websockets.connect(uri) as websocket:
        print("Connected to WebSocket")
        
        # Send a text message to initiate
        test_message = "Hello, Executive Sous-Chef! Can you help me with a recipe?"
        print(f"Sending text: {test_message}")
        await websocket.send(test_message)

        # Send dummy audio chunk
        print("Sending dummy audio chunk...")
        await websocket.send(b'\x00' * 3200) # 100ms of silence at 16kHz PCM16
        
        # Listen for response
        try:
            while True:
                response = await websocket.recv()
                if isinstance(response, str):
                    print(f"Received text: {response}")
                else:
                    print(f"Received binary data (audio): {len(response)} bytes")
        except websockets.exceptions.ConnectionClosed:
            print("Connection closed")

if __name__ == "__main__":
    asyncio.run(test_voice())
