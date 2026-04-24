from typing import Optional
from sqlmodel import SQLModel, Field

class LlmProvider(SQLModel, table=True):
    __tablename__ = "llm_providers"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, max_length=50)  # internal key: "gemini", "openai", etc.
    label: str = Field(max_length=100)  # display name: "Google Gemini", "OpenAI", etc.
