from pydantic import BaseModel

class KnowledgeQueryRequest(BaseModel):
    question: str
