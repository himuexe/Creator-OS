from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, BigInteger, CheckConstraint, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint, func, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, column_property, mapped_column
from sqlalchemy.types import TypeDecorator


def now():
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        # SQLite omits timezone information. All application writes use UTC.
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class Base(DeclarativeBase):
    pass


class Record:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now, onupdate=now)


class Workspace(Record, Base):
    __tablename__ = "workspaces"
    name: Mapped[str] = mapped_column(String(120))


class Source(Record, Base):
    __tablename__ = "sources"
    __table_args__ = (CheckConstraint("kind in ('video','script')", name="source_kind"),)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(12))
    filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(80))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    facts: Mapped[dict[str, Any]] = mapped_column("media_metadata", JSON)

    @property
    def content_url(self):
        return f"/api/v1/sources/{self.id}/content"


class Project(Record, Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint("workflow in ('video','script')", name="project_workflow"),
        CheckConstraint("status in ('draft','ready')", name="project_status"),
    )
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(2000), default="")
    workflow: Mapped[str] = mapped_column(String(12))
    status: Mapped[str] = mapped_column(String(12), default="draft")


Project.source_count = column_property(
    select(func.count(Source.id)).where(Source.project_id == Project.id)
    .correlate_except(Source).scalar_subquery()
)


class ProcessingJob(Record, Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (
        Index("uq_job_ingest_source", "source_id", unique=True,
              sqlite_where=text("kind = 'ingest'"), postgresql_where=text("kind = 'ingest'")),
        Index("uq_job_active_source", "source_id", unique=True,
              sqlite_where=text("status in ('queued','running')"), postgresql_where=text("status in ('queued','running')")),
        Index("ix_job_queue", "status", "created_at"),
    )
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(24), default="ingest")
    status: Mapped[str] = mapped_column(String(16), default="succeeded")
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    stage: Mapped[str] = mapped_column(String(24), default="complete", server_default="complete")
    progress: Mapped[int] = mapped_column(default=100, server_default="100")
    attempt: Mapped[int] = mapped_column(default=1, server_default="1")
    error: Mapped[str | None] = mapped_column(String(600))
    lease_token: Mapped[UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Transcript(Record, Base):
    __tablename__ = "transcripts"
    source_id: Mapped[UUID] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), unique=True)
    provider: Mapped[str] = mapped_column(String(120))
    model: Mapped[str] = mapped_column(String(160))
    language: Mapped[str] = mapped_column(String(32))
    topics: Mapped[list] = mapped_column(JSON, default=list)
    analysis_provider: Mapped[str | None] = mapped_column(String(120))
    analysis_model: Mapped[str | None] = mapped_column(String(160))


class TranscriptSegment(Record, Base):
    __tablename__ = "transcript_segments"
    __table_args__ = (UniqueConstraint("transcript_id", "position"), CheckConstraint('"end" > start AND start >= 0'))
    transcript_id: Mapped[UUID] = mapped_column(ForeignKey("transcripts.id", ondelete="CASCADE"))
    position: Mapped[int]
    start: Mapped[float] = mapped_column(Float)
    end: Mapped[float] = mapped_column(Float)
    text: Mapped[str] = mapped_column(Text)


class ContentSegment(Record, Base):
    __tablename__ = "content_segments"
    __table_args__ = (
        CheckConstraint('"end" > start AND start >= 0'),
        CheckConstraint("status in ('suggested','approved','rejected')"),
    )
    source_id: Mapped[UUID] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("processing_jobs.id", ondelete="CASCADE"))
    first: Mapped[int]
    last: Mapped[int]
    start: Mapped[float] = mapped_column(Float)
    end: Mapped[float] = mapped_column(Float)
    title: Mapped[str] = mapped_column(Text)
    hook: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    topic: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    transcript_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="suggested")
    provider: Mapped[str] = mapped_column(String(120))
    model: Mapped[str] = mapped_column(String(160))
