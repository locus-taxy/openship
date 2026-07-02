from pydantic import BaseModel

class GenerateOnboardingRequest(BaseModel):
    role: str
    company: str = "Locus"

class SubmitQuizAttemptRequest(BaseModel):
    answers: dict  # {"0": "a", "1": "b", ...}
