from pydantic import BaseModel

class KnowledgeQueryRequest(BaseModel):
    question: str

class ChatMessageRequest(BaseModel):
    question: str
