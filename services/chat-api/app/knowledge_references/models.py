from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class KnowledgeReference(BaseModel):
    model_config = ConfigDict(extra="ignore")
    scope: Literal["personal", "organization"]
    kind: Literal["document", "directory"]
    source_id: str = Field(min_length=1, max_length=128)
