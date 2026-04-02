from pydantic import BaseModel, Field

class SignupRequest(BaseModel):
    email: str = Field(..., description="User email")
    name: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=8)

class LoginRequest(BaseModel):
    email: str = Field(..., description="User email")
    password: str = Field(...)

class LoginResponse(BaseModel):
    user: dict
    access_token: str
    token_type: str = "bearer"
