"""Workspace-scoped video analysis requests and editorial review."""
from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .api import DB
from .config import PERSONAL_WORKSPACE
from .models import ContentSegment, ProcessingJob, Project, Source, Transcript, TranscriptSegment, now
from .schemas import AnalysisOut, ClipOut, ClipPatch, JobOut

router = APIRouter(prefix="/api/v1")
ACTIVE = ("queued", "running")


def video_source(db, source_id, *, lock=False):
    query = select(Source).join(Project).where(Source.id == source_id, Project.workspace_id == PERSONAL_WORKSPACE)
    source = db.scalar(query.with_for_update() if lock else query)
    if source is None:
        raise HTTPException(404, "Source could not be found.")
    if source.kind != "video":
        raise HTTPException(422, "Choose a recorded video for analysis.")
    return source


def job_for_workspace(db, job_id):
    job = db.scalar(select(ProcessingJob).join(Project).where(
        ProcessingJob.id == job_id, Project.workspace_id == PERSONAL_WORKSPACE))
    if job is None:
        raise HTTPException(404, "Job could not be found.")
    return job


def analysis_history(source_id):
    return select(ProcessingJob).where(ProcessingJob.source_id == source_id, ProcessingJob.kind != "ingest").order_by(
        ProcessingJob.created_at.desc(), ProcessingJob.id.desc())


def enqueue(db: Session, source_id: UUID, kind: str):
    source = video_source(db, source_id, lock=True)
    if not source.facts.get("audio_streams"):
        raise HTTPException(422, "This recording has no audio stream to transcribe.")
    history = analysis_history(source_id)
    existing = db.scalar(history.where(ProcessingJob.status.in_(ACTIVE)))
    if existing is not None:
        return existing
    if kind == "analyze":
        existing = db.scalar(history.where(ProcessingJob.kind == kind))
        if existing is not None:
            return existing
    else:
        analyzed = db.scalar(select(Transcript.analysis_provider).where(Transcript.source_id == source_id))
        if analyzed is None:
            raise HTTPException(409, "Complete an initial analysis before requesting alternative clips.")
    job = ProcessingJob(project_id=source.project_id, source_id=source_id, kind=kind,
                        status="queued", stage="queued", progress=0, attempt=0)
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        active = db.scalar(history.where(ProcessingJob.status.in_(ACTIVE)))
        if active is not None:
            return active
        raise
    return job


@router.post("/sources/{source_id}/analyze", response_model=JobOut, status_code=202)
def start_analysis(source_id: UUID, db: DB):
    return enqueue(db, source_id, "analyze")


@router.post("/sources/{source_id}/alternatives", response_model=JobOut, status_code=202)
def request_alternatives(source_id: UUID, db: DB):
    return enqueue(db, source_id, "alternatives")


@router.get("/sources/{source_id}/analysis", response_model=AnalysisOut)
def get_analysis(source_id: UUID, db: DB):
    video_source(db, source_id)
    job = db.scalar(analysis_history(source_id))
    transcript = db.scalar(select(Transcript).where(Transcript.source_id == source_id))
    result = None
    if transcript is not None:
        parts = db.scalars(select(TranscriptSegment).where(
            TranscriptSegment.transcript_id == transcript.id).order_by(TranscriptSegment.position)).all()
        result = dict(id=transcript.id, provider=transcript.provider, model=transcript.model,
                      language=transcript.language, segments=parts)
    clips = db.scalars(select(ContentSegment).where(ContentSegment.source_id == source_id)
                       .order_by(ContentSegment.created_at, ContentSegment.start)).all()
    return dict(source_id=source_id, job=job, transcript=result, topics=transcript.topics if transcript else [],
                provider=transcript.analysis_provider if transcript else None,
                model=transcript.analysis_model if transcript else None, clips=clips)


@router.get("/jobs/{job_id}", response_model=JobOut)
def job_detail(job_id: UUID, db: DB):
    return job_for_workspace(db, job_id)


@router.post("/jobs/{job_id}/retry", response_model=JobOut, status_code=202)
def retry(job_id: UUID, db: DB):
    job = job_for_workspace(db, job_id)
    video_source(db, job.source_id, lock=True)
    latest = db.scalar(analysis_history(job.source_id))
    if job.kind == "ingest" or latest is None or latest.id != job.id:
        raise HTTPException(409, "Retry the most recent analysis job.")
    if job.status in ACTIVE:
        return job
    changed = db.execute(update(ProcessingJob).where(
        ProcessingJob.id == job_id, ProcessingJob.status.in_(("failed", "cancelled"))
    ).values(status="queued", stage="queued", progress=0, error=None, finished_at=None))
    if not changed.rowcount:
        raise HTTPException(409, "Only failed or cancelled analysis jobs can be retried.")
    db.commit()
    db.refresh(job)
    return job


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
def cancel(job_id: UUID, db: DB):
    job = job_for_workspace(db, job_id)
    if job.status == "cancelled":
        return job
    changed = db.execute(update(ProcessingJob).where(
        ProcessingJob.id == job_id, ProcessingJob.kind != "ingest", ProcessingJob.status.in_(ACTIVE)
    ).values(status="cancelled", stage="cancelled", lease_token=None, lease_until=None, finished_at=now()))
    if not changed.rowcount:
        raise HTTPException(409, "Only queued or running analysis jobs can be cancelled.")
    db.commit()
    db.refresh(job)
    return job


@router.patch("/segments/{segment_id}", response_model=ClipOut)
def edit_segment(segment_id: UUID, payload: ClipPatch, db: DB):
    clip = db.scalar(select(ContentSegment).join(Source).join(Project).where(
        ContentSegment.id == segment_id, Project.workspace_id == PERSONAL_WORKSPACE).with_for_update())
    if clip is None:
        raise HTTPException(404, "Clip could not be found.")
    edits = payload.model_dump(exclude_unset=True)
    if {"start", "end"} & edits.keys():
        start, end = edits.get("start", clip.start), edits.get("end", clip.end)
        duration = db.get(Source, clip.source_id).facts["duration_seconds"]
        if not 0 <= start < end <= duration:
            raise HTTPException(422, "Set clip bounds within the video, with the end after the start.")
        parts = db.scalars(select(TranscriptSegment).join(Transcript).where(
            Transcript.source_id == clip.source_id, TranscriptSegment.start < end,
            TranscriptSegment.end > start).order_by(TranscriptSegment.position)).all()
        if not parts:
            raise HTTPException(422, "Choose a range that includes transcript text.")
        clip.first, clip.last = parts[0].position, parts[-1].position
        clip.transcript_text = " ".join(part.text for part in parts)
    for field, value in edits.items():
        setattr(clip, field, value)
    db.commit()
    return clip
