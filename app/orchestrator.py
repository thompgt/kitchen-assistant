import os
import json
import asyncio
from typing import List, Dict, Any, Optional, AsyncGenerator
import google.generativeai as genai
from dotenv import load_dotenv

from .tools import cooking_tools
from .schemas import RecipeState

load_dotenv()

class KitchenOrchestrator:
    def __init__(self):
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
        self.model = genai.GenerativeModel('gemini-1.5-flash') # Low-latency model
        self.system_prompt = (
            "You are an 'Executive Sous-Chef' voice assistant. Be concise, professional, and efficient. "
            "Help the chef manage recipes, timers, and conversions. Focus on high-speed kitchen operations."
        )
        self.history: Dict[str, List[Dict[str, Any]]] = {}

    def _get_tools(self) -> List[Any]:
        # Gemini uses actual functions for tool definition
        return [
            cooking_tools.set_kitchen_timer,
            cooking_tools.convert_units,
            cooking_tools.scale_recipe,
            cooking_tools.navigate_steps
        ]

    async def process_utterance(self, session_id: str, text: str) -> AsyncGenerator[str, None]:
        if session_id not in self.history:
            self.history[session_id] = [{"role": "user", "parts": [self.system_prompt]}] # Seed with system prompt
        
        # Tools in Gemini are passed via the chat session
        chat = self.model.start_chat(history=self.history[session_id], enable_automatic_function_calling=True)
        
        response = chat.send_message(text, stream=True)
        
        full_response = ""
        for chunk in response:
            if chunk.text:
                full_response += chunk.text
                yield chunk.text
        
        # Sync history back
        self.history[session_id] = chat.history
