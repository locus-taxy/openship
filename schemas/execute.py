from pydantic import BaseModel

class ExecuteRequest(BaseModel):
    language: str
    code: str

class ExecuteResponse(BaseModel):
    stdout: str
    stderr: str
