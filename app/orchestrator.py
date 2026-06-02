import os
import json
import asyncio
from typing import List, Dict, Any, Optional, AsyncGenerator
from anthropic import AsyncAnthropic
from dotenv import load_dotenv

from .tools import cooking_tools
from .schemas import RecipeState

load_dotenv()

class KitchenOrchestrator:
    def __init__(self):
        self.client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.model = "claude-3-5-sonnet-20240620"
        self.system_prompt = (
            "You are an 'Executive Sous-Chef' voice assistant. Be concise, professional, and efficient. "
            "Help the chef manage recipes, timers, and conversions. Focus on high-speed kitchen operations."
        )
        self.history: Dict[str, List[Dict[str, Any]]] = {}

    def _get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "set_kitchen_timer",
                "description": "Sets a new kitchen timer.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "duration_seconds": {"type": "integer", "description": "Duration in seconds"},
                        "label": {"type": "string", "description": "Label for the timer (e.g., 'Pasta')"}
                    },
                    "required": ["duration_seconds", "label"]
                }
            },
            {
                "name": "convert_units",
                "description": "Converts measurements between kitchen units.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "value": {"type": "number", "description": "Numeric value"},
                        "from_unit": {"type": "string", "description": "Source unit"},
                        "to_unit": {"type": "string", "description": "Target unit"}
                    },
                    "required": ["value", "from_unit", "to_unit"]
                }
            },
            {
                "name": "scale_recipe",
                "description": "Scales the recipe ingredients.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "multiplier": {"type": "number", "description": "Scaling factor (e.g., 2.0)"}
                    },
                    "required": ["multiplier"]
                }
            },
            {
                "name": "navigate_steps",
                "description": "Moves through recipe steps.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "direction": {"type": "string", "enum": ["next", "previous", "jump"]},
                        "step_index": {"type": "integer", "description": "Target index for jump"}
                    },
                    "required": ["direction"]
                }
            }
        ]

    async def _execute_tool(self, session_id: str, name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if name == "set_kitchen_timer":
            return await cooking_tools.set_kitchen_timer(session_id, **params)
        elif name == "convert_units":
            return await cooking_tools.convert_units(**params)
        elif name == "scale_recipe":
            return await cooking_tools.scale_recipe(session_id, **params)
        elif name == "navigate_steps":
            return await cooking_tools.navigate_steps(session_id, **params)
        return {"error": f"Tool {name} not found"}

    async def process_utterance(self, session_id: str, text: str) -> AsyncGenerator[str, None]:
        if session_id not in self.history:
            self.history[session_id] = []
        
        self.history[session_id].append({"role": "user", "content": text})
        
        # Tools loop
        while True:
            response_text = ""
            tool_uses = []
            
            async with self.client.messages.stream(
                model=self.model,
                max_tokens=1024,
                system=self.system_prompt,
                messages=self.history[session_id],
                tools=self._get_tool_schemas()
            ) as stream:
                async for event in stream:
                    if event.type == "text":
                        response_text += event.text
                        yield event.text
                    elif event.type == "tool_use":
                        tool_uses.append(event)

            if not tool_uses:
                self.history[session_id].append({"role": "assistant", "content": response_text})
                break
            
            # If tool used, execute and continue
            # Note: In a real streaming scenario, we might want to handle text + tool usage carefully
            self.history[session_id].append({"role": "assistant", "content": response_text or "Executing task..."})
            
            for tool in tool_uses:
                result = await self._execute_tool(session_id, tool.name, tool.input)
                self.history[session_id].append({
                    "role": "user", 
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool.id,
                            "content": json.dumps(result)
                        }
                    ]
                })
