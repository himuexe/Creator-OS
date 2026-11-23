"""Local CPU worker. The same leased job handler can be invoked by a queue consumer."""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
import logging
import math
from pathlib import Path
from threading import Event, Thread
import time
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import SQLAlchemyError

from .config import Settings
from .db import make_engine, session_factory
from .models import ContentSegment, ProcessingJob, Source, Transcript, TranscriptSegment, now
from .storage import LocalStorage

log = logging.getLogger(__name__)
LEASE_SECONDS = 90
MAX_INTERRUPTED_ATTEMPTS = 3


class JobError(Exception):
    """A message the creator can safely see."""


class LeaseLost(Exception):
    """A cancelled, deleted or reclaimed job cannot publish further changes."""


@dataclass(frozen=True)
class Claim:
    id: UUID
    token: UUID
    project_id: UUID
    source_id: UUID
    kind: str


def claim_next(factory, job_id=None):
    current = now()
    available = or_(ProcessingJob.status == "queued",
                    and_(ProcessingJob.status == "running", ProcessingJob.lease_until <= current))
    query = select(ProcessingJob).where(ProcessingJob.kind.in_(("analyze", "alternatives")), available)
    if job_id is not None:
        query = query.where(ProcessingJob.id == job_id)
    with factory.begin() as db:
        job = db.scalar(query.order_by(ProcessingJob.created_at).limit(1).with_for_update(skip_locked=True))
        if job is None:
            return None
        eligible = update(ProcessingJob).where(ProcessingJob.id == job.id, available).execution_options(synchronize_session=False)
        if job.status == "running" and job.attempt >= MAX_INTERRUPTED_ATTEMPTS:
            db.execute(eligible.values(status="failed", stage="failed", finished_at=current, lease_token=None,
                                       lease_until=None, error="Worker interrupted repeatedly. Retry when the worker is available."))
            return None
        token = uuid4()
        acquired = db.execute(eligible.values(status="running", stage="transcribing", attempt=ProcessingJob.attempt + 1,
                              progress=1, lease_token=token, lease_until=current + timedelta(seconds=LEASE_SECONDS)))
        if not acquired.rowcount:
            return None
        return Claim(job.id, token, job.project_id, job.source_id, job.kind)


def fenced_update(db, claim, **fields):
    """Acquire a database write lock and check ownership before every checkpoint."""
    fields.setdefault("lease_until", now() + timedelta(seconds=LEASE_SECONDS))
    changed = db.execute(update(ProcessingJob).where(
        ProcessingJob.id == claim.id, ProcessingJob.status == "running", ProcessingJob.lease_token == claim.token,
    ).values(**fields))
    if not changed.rowcount:
        raise LeaseLost()


@contextmanager
def heartbeats(factory, claim):
    stopped, lost = Event(), Event()

    def pulse():
        while not stopped.wait(LEASE_SECONDS / 3):
            try:
                with factory.begin() as db:
                    fenced_update(db, claim)
            except LeaseLost:
                lost.set()
                return
            except SQLAlchemyError:
                log.warning("Could not renew lease for job %s", claim.id)

    thread = Thread(target=pulse, name="job-heartbeat", daemon=True)
    thread.start()
    last_progress = -1

    def progress(fraction):
        nonlocal last_progress
        if lost.is_set():
            raise LeaseLost()
        value = max(2, min(80, int(fraction * 78 + 2)))
        if value > last_progress:
            with factory.begin() as db:
                fenced_update(db, claim, progress=value)
            last_progress = value

    try:
        yield progress
    finally:
        stopped.set()
        thread.join(timeout=5)


def transcribe_local(path, duration, progress):
    from .transcription import TranscriptionError, transcribe
    try:
        return transcribe(path, duration, progress)
    except TranscriptionError as exc:
        raise JobError(str(exc)) from exc


def recommend_clips(segments, *, duration, exclude):
    from .intelligence import AnalysisError, recommend
    try:
        return recommend(segments, duration=duration, exclude=exclude)
    except AnalysisError as exc:
        raise JobError(str(exc)) from exc


def save_speech(factory, claim, speech, duration):
    parts = []
    previous_start = 0
    for segment in speech.segments:
        start, end = float(segment.start), float(segment.end)
        if not (previous_start <= start < end <= duration + 0.05) or start >= duration:
            raise JobError("Transcription returned invalid timestamps. Check the source and retry.")
        text = segment.text.strip()
        if not text or "\x00" in text:
            raise JobError("Transcription returned an invalid speech segment.")
        parts.append(dict(position=len(parts), start=start, end=min(end, duration), text=text))
        previous_start = start
    if not parts:
        raise JobError("No speech was detected in this recording.")
    with factory.begin() as db:
        fenced_update(db, claim, stage="recommending", progress=82)
        transcript = Transcript(source_id=claim.source_id, language=speech.language, provider=speech.provider, model=speech.model)
        db.add(transcript)
        db.flush()
        db.add_all(TranscriptSegment(transcript_id=transcript.id, **part) for part in parts)


def similar_range(start, end, existing):
    for left, right in existing:
        overlap = max(0, min(end, right) - max(start, left))
        if overlap >= 0.85 * (max(end, right) - min(start, left)):
            return True
    return False


def analyze(factory, claim, config, transcribe, recommend, progress):
    with factory() as db:
        source = db.get(Source, claim.source_id)
        if source is None:
            raise LeaseLost()
        duration = float(source.facts["duration_seconds"])
        if not math.isfinite(duration) or duration <= 0:
            raise JobError("This source has an invalid duration.")
        transcript_id = db.scalar(select(Transcript.id).where(Transcript.source_id == source.id))
    if transcript_id is None:
        path = LocalStorage(config.storage_root).location(claim.project_id, claim.source_id)
        if not path.is_file():
            raise JobError("The original source is missing. Restore its file or upload the recording again.")
        speech = transcribe(path, duration, progress)
        save_speech(factory, claim, speech, duration)

    with factory.begin() as db:
        fenced_update(db, claim, stage="recommending", progress=85)
        transcript = db.scalar(select(Transcript).where(Transcript.source_id == claim.source_id))
        transcript_id = transcript.id
        segments = [dict(start=p.start, end=p.end, text=p.text) for p in db.scalars(
            select(TranscriptSegment).where(TranscriptSegment.transcript_id == transcript_id).order_by(TranscriptSegment.position))]
        existing = db.execute(select(ContentSegment.start, ContentSegment.end).where(ContentSegment.source_id == claim.source_id)).all()
    plan = recommend(segments, duration=duration, exclude=[(r.start, r.end) for r in existing])

    with factory.begin() as db:
        fenced_update(db, claim, status="succeeded", stage="complete", progress=100,
                      finished_at=now(), lease_token=None, lease_until=None)
        transcript = db.get(Transcript, transcript_id)
        # Alternatives always append. Edits made while the provider worked remain authoritative.
        existing = list(db.execute(select(ContentSegment.start, ContentSegment.end)
                                    .where(ContentSegment.source_id == claim.source_id)).all())
        for clip in plan.clips:
            if not 0 <= clip.first <= clip.last < len(segments):
                raise JobError("Analysis referenced an unknown transcript segment.")
            passage = segments[clip.first:clip.last + 1]
            start, end = passage[0]["start"], passage[-1]["end"]
            if similar_range(start, end, existing):
                continue
            fields = {key: getattr(clip, key) for key in ("first", "last", "title", "hook", "description", "topic", "reason")}
            db.add(ContentSegment(**fields, source_id=claim.source_id, job_id=claim.id, start=start, end=end,
                                  transcript_text=" ".join(p["text"] for p in passage), provider=plan.provider, model=plan.model))
            existing.append((start, end))
        transcript.topics = list(dict.fromkeys([*transcript.topics, *plan.topics]))
        transcript.analysis_provider, transcript.analysis_model = plan.provider, plan.model


def run_one(config: Settings, factory, job_id: UUID | None = None, *, transcriber=transcribe_local, recommender=recommend_clips):
    claim = claim_next(factory, job_id)
    if claim is None:
        return False
    try:
        with heartbeats(factory, claim) as progress:
            analyze(factory, claim, config, transcriber, recommender, progress)
    except LeaseLost:
        pass
    except Exception as exc:
        message = str(exc) if isinstance(exc, JobError) else "Analysis could not finish. Check worker configuration and retry."
        log.warning("Analysis job %s failed (%s)", claim.id, type(exc).__name__)
        try:
            with factory.begin() as db:
                fenced_update(db, claim, status="failed", stage="failed", error=message[:600], finished_at=now(),
                              lease_token=None, lease_until=None)
        except LeaseLost:
            pass
    return True


def main():
    config = Settings.from_env()
    engine = make_engine(config.database_url)
    factory = session_factory(engine)
    logging.basicConfig(level=logging.INFO)
    log.info("CPU analysis worker ready.")
    try:
        while True:
            try:
                processed = run_one(config, factory)
            except SQLAlchemyError:
                log.warning("Analysis database is unavailable. Reconnecting.")
                time.sleep(3)
                continue
            if not processed:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
