from typing import List
from pydantic import BaseModel

class IngestRequest(BaseModel):
    space_keys: List[str]

class ConfirmCandidatesRequest(BaseModel):
    page_ids: List[str]
