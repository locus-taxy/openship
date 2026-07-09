from pydantic import BaseModel

class GenerateOnboardingRequest(BaseModel):
    role: str
    # company is NOT taken from the client — it's resolved server-side from the
    # user's tenant so plans are always branded with the correct company.

class SubmitQuizAttemptRequest(BaseModel):
    answers: dict  # {"0": "a", "1": "b", ...}
