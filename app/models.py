from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime

class Ingredient(BaseModel):
    name: str
    amount: float
    unit: str

class RecipeStep(BaseModel):
    step_number: int
    instruction: str
    duration_minutes: Optional[int] = None

class RecipeMetadata(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    ingredients: List[Ingredient]
    steps: List[RecipeStep]
    total_time_minutes: int

class KitchenTimer(BaseModel):
    id: str
    label: str
    duration_seconds: int
    start_time: datetime
    remaining_seconds: int
    is_active: bool = True

class RecipeState(BaseModel):
    session_id: str
    recipe_id: Optional[str] = None
    current_step_index: int = 0
    active_timers: Dict[str, KitchenTimer] = {}
    last_updated: datetime = Field(default_factory=datetime.now)

class UserUtterance(BaseModel):
    text: str
    session_id: str

class AgentResponse(BaseModel):
    text: str
    session_id: str
    state: RecipeState
