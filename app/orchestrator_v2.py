import os
import asyncio
import json
from typing import List, Dict, Any, Optional
import google.generativeai as genai
from dotenv import load_dotenv

from .tools import cooking_tools

load_dotenv()

class KitchenOrchestrator:
    def __init__(self):
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
        self.model = genai.GenerativeModel('gemini-1.5-flash-latest')
        self.system_prompt = (
            "You are an 'Executive Sous-Chef' voice assistant. Be concise, professional, and efficient. "
            "Help the chef manage recipes, timers, and conversions. Focus on high-speed kitchen operations."
        )
        self.history = []
        self.audio_buffer = bytearray()
        self.is_processing = False

    async def handle_voice_session(self, websocket):
        """
        Handles a bi-directional voice session by buffering audio and processing with Gemini.
        """
        try:
            while True:
                message = await websocket.receive()
                
                if "bytes" in message:
                    # Buffer audio bytes
                    self.audio_buffer.extend(message["bytes"])
                    
                    # Simple logic: If we have > 3 seconds of audio, process it
                    # (In a real app, we'd use VAD)
                    if len(self.audio_buffer) > 16000 * 2 * 3: # 3 seconds at 16kHz PCM16
                        await self._process_buffer(websocket)
                
                elif "text" in message:
                    # Handle text directly
                    await self._process_text(websocket, message["text"])
                    
        except Exception as e:
            print(f"Orchestrator session error: {e}")

    async def _process_buffer(self, websocket):
        if self.is_processing:
            return
        
        self.is_processing = True
        print("Processing audio buffer...")
        
        try:
            # For simplicity, we wrap the raw PCM in a WAV header or just send to Gemini if it supports raw
            # Gemini 1.5 supports many audio formats.
            # We'll use a placeholder for the actual audio-to-content call
            
            # Extract current buffer
            audio_data = bytes(self.audio_buffer)
            self.audio_buffer.clear()
            
            # Send to Gemini
            # Note: We use the multimodal prompt
            response = await asyncio.to_thread(
                self.model.generate_content,
                [
                    self.system_prompt,
                    {"mime_type": "audio/pcm;rate=16000", "data": audio_data}
                ]
            )
            
            if response.text:
                await websocket.send_text(json.dumps({"type": "text", "content": response.text}))
                
        except Exception as e:
            print(f"Error processing audio: {e}")
        finally:
            self.is_processing = False

    async def _process_text(self, websocket, text):
        print(f"Processing text: {text}")
        chat = self.model.start_chat(history=self.history, enable_automatic_function_calling=True)
        response = await asyncio.to_thread(chat.send_message, text)
        
        if response.text:
            await websocket.send_text(json.dumps({"type": "text", "content": response.text}))
        
        self.history = chat.history
