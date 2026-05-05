from typing import Dict, List, Optional
from pydantic import BaseModel

class QuizGenerateResponse(BaseModel):
    quiz_id: int
    status: str
    question_count: int
    pass_score: int

class QuizQuestionOut(BaseModel):
    id: int
    position: int
    question: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    # correct_option intentionally omitted

class QuizOut(BaseModel):
    quiz_id: int
    skill_id: int
    difficulty: str
    pass_score: int
    status: str
    questions: List[QuizQuestionOut]
    best_score: Optional[int]
    attempt_count: int

class QuizSubmitRequest(BaseModel):
    answers: Dict[int, str]  # { question_id: "A" | "B" | "C" | "D" }

class QuizQuestionResult(BaseModel):
    question_id: int
    selected: str
    correct: str
    is_correct: bool
    explanation: str

class QuizSubmitResponse(BaseModel):
    attempt_id: int
    score: int
    passed: bool
    pass_score: int
    results: List[QuizQuestionResult]

class QuizAttemptOut(BaseModel):
    attempt_id: int
    score: int
    passed: bool
    created_at: str

class QuizAttemptsResponse(BaseModel):
    quiz_id: int
    skill_id: int
    pass_score: int
    attempts: List[QuizAttemptOut]
