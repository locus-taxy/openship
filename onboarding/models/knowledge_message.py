from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Column, DateTime, func

class KnowledgeMessage(SQLModel, table=True):
    """One turn in a KnowledgeChat. `role` is 'user' or 'assistant'; assistant
    turns carry a JSON list of citations. Deleted with their parent chat."""

    __tablename__ = "knowledge_messages"

    id: Optional[int] = Field(default=None, primary_key=True)
    chat_id: int = Field(foreign_key="knowledge_chats.id", index=True, ondelete="CASCADE")
    role: str = Field(max_length=16)  # user | assistant
    content: str  # user question, or a plain-text flattening of an assistant answer
    blocks: Optional[str] = Field(default=None)  # JSON TEXT of structured ContentBlocks
    citations: Optional[str] = Field(default=None)  # JSON TEXT: [{title, page_id}]
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now()),
    )
