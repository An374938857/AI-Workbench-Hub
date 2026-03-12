from typing import Optional

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=6, max_length=50)
    display_name: str = Field(..., min_length=1, max_length=50)
    role: str = Field("user", pattern="^(user|provider|admin)$")


class UserUpdate(BaseModel):
    display_name: Optional[str] = Field(None, min_length=1, max_length=50)
    role: Optional[str] = Field(None, pattern="^(user|provider|admin)$")
    is_active: Optional[bool] = None


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=6, max_length=50)


class UserResponse(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    is_active: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True
