import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.resume import ResumeLanguage

MAX_RESUME_CHARS = 30000


class ResumeIn(BaseModel):
    content_md: str = Field(min_length=20, max_length=MAX_RESUME_CHARS)


class ResumeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    language: ResumeLanguage
    content_md: str
    source: str
    filename: str | None
    updated_at: datetime
