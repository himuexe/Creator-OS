from io import BytesIO
import logging
from shutil import rmtree
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import PERSONAL_WORKSPACE, Settings
from .limits import BODY_LIMIT_ERROR, ENVELOPE_BYTES, exceeds_declared_limit
from .models import ProcessingJob, Project, Source, Workspace
from .schemas import Health, JobOut, ProjectCreate, ProjectOut, ProjectPatch, ScriptInput, SourceOut
from .services import get_project, ingest, project_workflow
from .storage import LocalStorage

router = APIRouter(prefix="/api/v1")
log = logging.getLogger(__name__)


def session(request: Request):
    with request.app.state.sessions() as db:
        yield db


def settings(request: Request):
    return request.app.state.config


DB = Annotated[Session, Depends(session)]
Config = Annotated[Settings, Depends(settings)]


@router.get("/health", response_model=Health)
def health(db: DB, config: Config):
    if db.get(Workspace, PERSONAL_WORKSPACE) is None:
        raise HTTPException(503, "The workspace has not been initialized. Run the database migration.")
    return {"status": "ok", "max_video_bytes": config.max_video_bytes, "max_script_bytes": config.max_script_bytes}


@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(payload: ProjectCreate, db: DB):
    project = Project(workspace_id=PERSONAL_WORKSPACE, **payload.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(db: DB):
    return db.scalars(select(Project).where(Project.workspace_id == PERSONAL_WORKSPACE)
                      .order_by(Project.updated_at.desc(), Project.id)).all()


@router.get("/projects/{project_id}", response_model=ProjectOut)
def project_detail(project_id: UUID, db: DB):
    return get_project(db, project_id)


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def edit_project(project_id: UUID, payload: ProjectPatch, db: DB):
    project = get_project(db, project_id, lock=True)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, key, value)
    db.commit()
    db.refresh(project)
    return project


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: UUID, db: DB, config: Config):
    project = get_project(db, project_id, lock=True)
    directory = config.storage_root / "sources" / project.id.hex
    db.delete(project)
    db.commit()
    # Readers lose access at commit. A crash during cleanup can leave only unreachable bytes.
    try:
        rmtree(directory)
    except FileNotFoundError:
        pass
    except OSError:
        log.warning("Deferred cleanup of deleted project %s.", project_id, exc_info=True)
    return Response(status_code=204)


@router.post("/projects/{project_id}/scripts", response_model=SourceOut, status_code=201)
def create_script(project_id: UUID, payload: ScriptInput, config: Config, db: DB):
    try:
        data = payload.text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise HTTPException(422, "Script must contain valid Unicode text.") from exc
    return ingest(db, config, project_id, payload.filename, BytesIO(data), direct=True)


@router.post("/projects/{project_id}/sources", response_model=SourceOut, status_code=201, openapi_extra={
    "requestBody": {"required": True, "content": {"multipart/form-data": {"schema": {
        "type": "object", "required": ["file"], "properties": {"file": {"type": "string", "format": "binary"}},
    }}}},
})
async def upload_source(project_id: UUID, request: Request, config: Config, db: DB):
    if request.headers.get("content-type", "").partition(";")[0].lower() != "multipart/form-data":
        raise HTTPException(415, "Send the source as multipart/form-data.")
    workflow = await run_in_threadpool(project_workflow, db, project_id)
    limit = config.max_video_bytes if workflow == "video" else config.max_script_bytes
    request.state.body_limit = limit + ENVELOPE_BYTES
    if exceeds_declared_limit(request.headers, request.state.body_limit):
        raise HTTPException(413, BODY_LIMIT_ERROR)
    try:
        async with request.form(max_files=1, max_fields=0) as form:
            file = form.get("file")
            if not isinstance(file, UploadFile):
                raise HTTPException(422, "Send one file in the multipart file field.")
            return await run_in_threadpool(ingest, db, config, project_id, file.filename or "", file.file, workflow=workflow)
    except StarletteHTTPException as exc:
        if exc.detail == BODY_LIMIT_ERROR:
            raise HTTPException(413, BODY_LIMIT_ERROR) from exc
        raise


@router.get("/projects/{project_id}/sources", response_model=list[SourceOut])
def list_sources(project_id: UUID, db: DB):
    get_project(db, project_id)
    return db.scalars(select(Source).where(Source.project_id == project_id).order_by(Source.created_at.desc())).all()


@router.get("/sources/{source_id}/content", response_class=FileResponse)
def source_content(source_id: UUID, db: DB, config: Config):
    source = db.scalar(select(Source).join(Project).where(Source.id == source_id, Project.workspace_id == PERSONAL_WORKSPACE))
    if source is None:
        raise HTTPException(404, "Source could not be found.")
    path = LocalStorage(config.storage_root).location(source.project_id, source.id)
    if not path.is_file():
        raise HTTPException(410, "The stored source file is unavailable.")
    return FileResponse(path, filename=source.filename, media_type=source.media_type,
                        content_disposition_type="inline", headers={
                            "X-Content-Type-Options": "nosniff", "Cross-Origin-Resource-Policy": "same-origin",
                            "Cache-Control": "private, no-store", "Content-Security-Policy": "sandbox",
                        })


def workspace_jobs():
    return select(ProcessingJob).join(Project).where(Project.workspace_id == PERSONAL_WORKSPACE).order_by(ProcessingJob.created_at.desc())


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(db: DB):
    return db.scalars(workspace_jobs()).all()


@router.get("/projects/{project_id}/jobs", response_model=list[JobOut])
def project_jobs(project_id: UUID, db: DB):
    get_project(db, project_id)
    return db.scalars(workspace_jobs().where(ProcessingJob.project_id == project_id)).all()
