from pathlib import Path
from typing import BinaryIO
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import PERSONAL_WORKSPACE, Settings
from .media import inspect_video
from .models import ProcessingJob, Project, Source, now
from .storage import LocalStorage


VIDEO_TYPES = {".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm", ".mkv": "video/x-matroska"}
SCRIPT_TYPES = {".txt": "text/plain", ".md": "text/plain"}


def get_project(db: Session, project_id: UUID, *, lock=False):
    query = select(Project).where(Project.id == project_id, Project.workspace_id == PERSONAL_WORKSPACE)
    if lock:
        query = query.with_for_update()
    project = db.scalar(query)
    if project is None:
        raise HTTPException(404, "Project could not be found.")
    return project


def display_name(filename: str):
    name = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not name or len(name) > 255 or any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise HTTPException(422, "Supply a valid filename up to 255 characters.")
    return name


def script_facts(path: Path):
    try:
        text = path.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(422, "Script files must use UTF-8 text encoding.") from exc
    if not text.strip() or any(ord(c) < 32 and c not in "\r\n\t" for c in text):
        raise HTTPException(422, "A script must contain readable, nonblank text.")
    return {"characters": len(text), "word_count": len(text.split())}


def project_workflow(db: Session, project_id: UUID):
    workflow = get_project(db, project_id).workflow
    db.rollback()  # Release the read transaction before receiving or inspecting large files.
    return workflow


def ingest(db: Session, config: Settings, project_id: UUID, filename: str, stream: BinaryIO, *, direct=False, workflow=None):
    workflow = workflow or project_workflow(db, project_id)
    if direct and workflow != "script":
        raise HTTPException(422, "Direct script input requires a script project.")
    name = display_name(filename)
    extension = Path(name).suffix.lower()
    allowed = VIDEO_TYPES if workflow == "video" else SCRIPT_TYPES
    if extension not in allowed:
        raise HTTPException(415, f"Choose a {workflow} file ending in {', '.join(allowed)}.")
    limit = config.max_video_bytes if workflow == "video" else config.max_script_bytes
    storage = LocalStorage(config.storage_root)
    source_id = uuid4()
    destination = storage.location(project_id, source_id)
    started_at = now()
    with storage.stage(stream, limit) as (temporary, size):
        facts = inspect_video(temporary, extension, config.ffprobe_bin) if workflow == "video" else script_facts(temporary)
        # Serialize final attachment against project deletion in PostgreSQL.
        project = get_project(db, project_id, lock=True)
        source = Source(id=source_id, project_id=project_id, kind=workflow, filename=name,
                        media_type=allowed[extension], size_bytes=size, facts=facts)
        project.status = "ready"
        project.updated_at = now()
        db.add(source)
        db.flush()
        db.add(ProcessingJob(project_id=project_id, source_id=source_id, created_at=started_at, finished_at=now()))
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary.replace(destination)
        try:
            db.commit()
        except Exception:
            db.rollback()
            # A lost commit acknowledgement can occur after the server persisted the source.
            # Keep its bytes if the outcome cannot be confirmed against the database.
            committed = db.scalar(select(Source).where(Source.id == source_id))
            if committed is not None:
                return committed
            destination.unlink(missing_ok=True)
            raise
    return source
