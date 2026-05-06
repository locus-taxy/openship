from typing import Literal
from pydantic import BaseModel, Field

class SubscribeRequest(BaseModel):
    skill: str = Field(..., description="Skill the user wants to learn")
    days: int = Field(90, gt=0, description="Number of days for the syllabus")
    hours: int = Field(1, gt=0, description="Hours per day the user will study")
    quiz_difficulty: Literal["beginner", "intermediate", "advanced"] = "beginner"

class GenerateSyllabusRequest(BaseModel):
    skill: str = Field(..., description="Skill to generate syllabus for")

class GenerateContentRequest(BaseModel):
    skill_id: int = Field(..., description="Skill ID to generate content for")

class GenerateChapterContentRequest(BaseModel):
    task_id: int = Field(..., description="Task ID to generate content for")

class SendChapterEmailRequest(BaseModel):
    task_id: int = Field(..., description="Task ID to send email for")
