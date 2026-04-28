from typing import Optional
from sqlmodel import SQLModel, Field, Column
from sqlalchemy import Integer, ForeignKey, Text

class QuizQuestion(SQLModel, table=True):
    __tablename__ = "quiz_questions"

    id: Optional[int] = Field(default=None, primary_key=True)
    quiz_id: int = Field(
        sa_column=Column(Integer, ForeignKey("quizzes.id", ondelete="CASCADE"), index=True)
    )
    position: int
    question: str = Field(sa_column=Column(Text))
    option_a: str = Field(sa_column=Column(Text))
    option_b: str = Field(sa_column=Column(Text))
    option_c: str = Field(sa_column=Column(Text))
    option_d: str = Field(sa_column=Column(Text))
    correct_option: str  # "A" | "B" | "C" | "D" — never sent to frontend before submission
    explanation: str = Field(sa_column=Column(Text))
