from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator


Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Description = Annotated[str, StringConstraints(max_length=2000)]
Workflow = Literal["video", "script"]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("name", "description", check_fields=False)
    @classmethod
    def valid_database_text(cls, value):
        if value is not None and "\x00" in value:
            raise ValueError("Text cannot contain a null character.")
        return value


class ProjectCreate(Input):
    name: Name
    workflow: Workflow
    description: Description = ""


class ProjectPatch(Input):
    name: Name | None = None
    description: Description | None = None

    @model_validator(mode="after")
    def supplied_fields(self):
        if not self.model_fields_set or any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("Supply a name or description to update.")
        return self


class ScriptInput(Input):
    text: str
    filename: Annotated[str, StringConstraints(min_length=1, max_length=255)] = "script.txt"


class Output(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProjectOut(Output):
    id: UUID
    name: str
    description: str
    workflow: Workflow
    status: Literal["draft", "ready"]
    source_count: int
    created_at: datetime
    updated_at: datetime


class SourceOut(Output):
    id: UUID
    project_id: UUID
    kind: Workflow
    filename: str
    media_type: str
    size_bytes: int
    metadata: dict = Field(validation_alias="facts")
    content_url: str
    created_at: datetime


class JobOut(Output):
    id: UUID
    project_id: UUID
    source_id: UUID
    kind: Literal["ingest", "analyze", "alternatives"]
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    created_at: datetime
    finished_at: datetime | None
    stage: str
    progress: int
    attempt: int
    error: str | None


class TranscriptPartOut(Output):
    id: UUID
    position: int
    start: float
    end: float
    text: str


class TranscriptOut(Output):
    id: UUID
    language: str
    provider: str
    model: str
    segments: list[TranscriptPartOut]


Review = Literal["suggested", "approved", "rejected"]


class ClipOut(Output):
    id: UUID
    source_id: UUID
    start: float
    end: float
    title: str
    hook: str
    topic: str
    reason: str
    description: str
    transcript_text: str
    status: Review
    provider: str
    model: str


class ClipPatch(Input):
    start: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None
    end: Annotated[float, Field(gt=0, allow_inf_nan=False)] | None = None
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=240)] | None = None
    hook: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)] | None = None
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=3000)] | None = None
    status: Review | None = None

    @model_validator(mode="after")
    def valid_edit(self):
        values = self.model_dump(exclude_unset=True).values()
        if not self.model_fields_set or any(v is None or (isinstance(v, str) and "\x00" in v) for v in values):
            raise ValueError("Provide at least one non-null clip edit.")
        return self


class AnalysisOut(Output):
    source_id: UUID
    job: JobOut | None
    transcript: TranscriptOut | None
    topics: list[str]
    provider: str | None
    model: str | None
    clips: list[ClipOut]


class Health(Output):
    status: Literal["ok"]
    max_video_bytes: int
    max_script_bytes: int
