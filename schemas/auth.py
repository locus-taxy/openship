from typing import Optional
from pydantic import BaseModel, EmailStr, Field

class SignupRequest(BaseModel):
    email: EmailStr
    name: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=8)

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(...)

class SaveSettingsRequest(BaseModel):
    llm_provider: Optional[str] = Field(default=None, max_length=50)
    llm_model: Optional[str] = Field(default=None, max_length=100)
    api_key: Optional[str] = Field(default=None, max_length=512)
