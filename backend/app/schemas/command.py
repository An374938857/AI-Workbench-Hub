from pydantic import BaseModel
from typing import Optional, Dict, Any


class CommandCreate(BaseModel):
    name: str
    description: str
    action_type: str
    action_params: Optional[Dict[str, Any]] = None


class CommandResponse(BaseModel):
    id: int
    name: str
    description: str
    action_type: str
    action_params: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True
