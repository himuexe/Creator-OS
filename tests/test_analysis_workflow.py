"""Durable analysis orchestration with controlled, deterministic provider responses."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Event
from types import SimpleNamespace as Result
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select, text

from app.config import PERSONAL_WORKSPACE
from app.db import make_engine
from app.models import ProcessingJob, Project, Source, Workspace, now
from app.storage import LocalStorage
from app.worker import JobError, LeaseLost, claim_next, fenced_update, run_one

API = "/api/v1"


@pytest.fixture
def source(client, config):
    project = client.post(API + "/projects", json={"name": "Test lecture", "workflow": "video"}).json()
    with client.app.state.sessions.begin() as db:
        row = Source(project_id=UUID(project["id"]), kind="video", filename="lecture.mp4", size_bytes=4,
                     media_type="video/mp4", facts={"duration_seconds": 20.0, "audio_streams": 1})
        db.add(row)
        db.flush()
        location = LocalStorage(config.storage_root).location(row.project_id, row.id)
        location.parent.mkdir(parents=True, exist_ok=True)
        location.write_bytes(b"stub")
        return row.id


def speech(path, duration, progress):
    assert path.read_bytes() == b"stub" and duration == 20
    progress(0.5)
    return Result(provider="test speech", model="fixture", language="en", segments=[
        Result(start=1, end=3.5, text="How does evaporation work?"),
        Result(start=4, end=7, text="Some molecules gain enough energy to leave the surface."),
        Result(start=10, end=16, text="Condensation releases this energy."),
    ])


def select_clips(segments, *, duration, exclude):
    assert duration == 20 and len(segments) == 3
    first, last = (2, 2) if exclude else (0, 1)
    return Result(provider="test analyst", model="fixture", topics=["Water cycle"], clips=[
        Result(first=first, last=last, title="Phase changes", hook="What happens to water?",
               description="A complete explanation", topic="Water cycle", reason="Explains a physical mechanism.")
    ])


def test_queue_review_and_alternatives(client, config, source):
    factory = client.app.state.sessions
    url = f"{API}/sources/{source}"
    empty = client.get(url + "/analysis").json()
    assert empty["clips"] == [] and empty["job"] is None and empty["transcript"] is None
    assert client.post(url + "/alternatives").status_code == 409
    job = client.post(url + "/analyze").json()
    assert job["status"] == "queued" and job["finished_at"] is None
    assert job["id"] == client.post(url + "/analyze").json()["id"]
    assert run_one(config, factory, transcriber=speech, recommender=select_clips)
    assert not run_one(config, factory, transcriber=speech, recommender=select_clips)
    analysis = client.get(url + "/analysis").json()
    assert analysis["job"]["status"] == "succeeded" and analysis["job"]["progress"] == 100
    assert analysis["transcript"]["language"] == "en" and len(analysis["transcript"]["segments"]) == 3
    assert analysis["topics"] == ["Water cycle"] and analysis["provider"] == "test analyst"
    clip = analysis["clips"][0]
    assert (clip["start"], clip["end"], clip["source_id"]) == (1, 7, str(source))
    endpoint = f"{API}/segments/{clip['id']}"
    for invalid in ({"start": -1}, {"end": 20.1}, {"start": 8, "end": 9}, {"end": 1}, {"title": None}):
        assert client.patch(endpoint, json=invalid).status_code == 422
    edited = client.patch(endpoint, json={"start": 4.5, "end": 6.9, "status": "approved", "title": "Edited"}).json()
    assert edited["transcript_text"] == "Some molecules gain enough energy to leave the surface."
    alternative = client.post(url + "/alternatives").json()
    assert alternative["id"] != job["id"] and alternative["kind"] == "alternatives"
    assert run_one(config, factory, transcriber=lambda *a: pytest.fail("Unexpected ASR call"), recommender=select_clips)
    result = client.get(url + "/analysis").json()
    assert len(result["clips"]) == 2 and result["clips"][0] == edited
    assert client.patch(endpoint, json={"status": "rejected"}).json()["status"] == "rejected"
    assert {j["id"] for j in client.get(API + "/jobs").json()} == {job["id"], alternative["id"]}


def test_failed_analysis_reuses_durable_transcript(client, config, source):
    factory = client.app.state.sessions
    url = f"{API}/sources/{source}"
    job_url = API + "/jobs/" + client.post(url + "/analyze").json()["id"]

    def unavailable(*args, **kwargs):
        raise JobError("Local analysis provider unavailable.")

    run_one(config, factory, transcriber=speech, recommender=unavailable)
    state = client.get(url + "/analysis").json()
    assert state["transcript"] and not state["clips"]
    assert state["job"]["status"] == "failed" and state["job"]["error"] == "Local analysis provider unavailable."
    assert client.post(job_url + "/retry").status_code == 202
    run_one(config, factory, transcriber=lambda *a: pytest.fail("Repeated transcription"), recommender=select_clips)
    success = client.get(job_url).json()
    assert (success["status"], success["attempt"], success["error"]) == ("succeeded", 2, None)
    assert client.get(url + "/analysis").json()["transcript"]["id"] == state["transcript"]["id"]


def test_worker_lease_fences_cancelled_and_reclaimed_runs(client, config, source):
    factory = client.app.state.sessions
    job_url = API + "/jobs/" + client.post(f"{API}/sources/{source}/analyze").json()["id"]
    first = claim_next(factory)
    assert claim_next(factory) is None
    with factory.begin() as db:
        db.get(ProcessingJob, first.id).lease_until = now() - timedelta(seconds=1)
    second = claim_next(factory)
    assert second.id == first.id and second.token != first.token
    with pytest.raises(LeaseLost), factory.begin() as db:
        fenced_update(db, first, progress=99)
    assert client.post(job_url + "/cancel").json()["status"] == "cancelled"
    with pytest.raises(LeaseLost), factory.begin() as db:
        fenced_update(db, second, progress=99)
    assert client.post(job_url + "/retry").json()["status"] == "queued"
    assert run_one(config, factory, transcriber=speech, recommender=select_clips)
    assert client.get(job_url).json()["attempt"] == 3


def test_cancellation_during_inference(client, config, source):
    factory = client.app.state.sessions
    url = f"{API}/sources/{source}"
    job_url = API + "/jobs/" + client.post(url + "/analyze").json()["id"]
    started, resume = Event(), Event()

    def paused(path, duration, progress):
        started.set()
        assert resume.wait(timeout=10)
        return speech(path, duration, progress)

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(run_one, config, factory, transcriber=paused, recommender=select_clips)
        try:
            assert started.wait(timeout=10)
            assert not run_one(config, factory, transcriber=speech, recommender=select_clips)
            assert client.post(job_url + "/cancel").status_code == 200
        finally:
            resume.set()
        pending.result(timeout=10)
    assert client.get(url + "/analysis").json()["transcript"] is None
    assert client.get(job_url).json()["status"] == "cancelled"


def test_analysis_workspace_isolation_and_no_audio(client, config, source):
    factory = client.app.state.sessions
    url = f"{API}/sources/{source}"
    job = client.post(url + "/analyze").json()
    run_one(config, factory, transcriber=speech, recommender=select_clips)
    clip = client.get(url + "/analysis").json()["clips"][0]
    with factory.begin() as db:
        row = db.get(Source, source)
        row.facts = {"audio_streams": 0, "duration_seconds": 20}
    assert client.post(url + "/analyze").status_code == 422
    with factory.begin() as db:
        other = Workspace(name="Another creator")
        db.add(other)
        db.flush()
        db.get(Project, UUID(job["project_id"])).workspace_id = other.id
    for response in (client.get(url + "/analysis"), client.post(url + "/analyze"), client.post(url + "/alternatives"),
                     client.get(API + "/jobs/" + job["id"]), client.post(API + "/jobs/" + job["id"] + "/cancel"),
                     client.patch(API + "/segments/" + clip["id"], json={"start": 2})):
        assert response.status_code == 404


def test_migrate_populated_foundation(database_url):
    backend = Path(__file__).resolve().parents[1] / "backend"
    migration = Config(str(backend / "alembic.ini"))
    migration.attributes["database_url"] = database_url
    command.upgrade(migration, "0001_foundation")
    engine = make_engine(database_url)
    project, source, job = (uuid4().hex for _ in range(3))
    ts = now()
    with engine.begin() as db:
        db.execute(text("INSERT INTO projects (id, created_at, updated_at, workspace_id, name, description, workflow, status) "
                        "VALUES (:id,:ts,:ts,:workspace,'Lecture','','video','ready')"),
                   dict(id=project, ts=ts, workspace=PERSONAL_WORKSPACE.hex))
        db.execute(text("INSERT INTO sources (id, created_at, updated_at, project_id, kind, filename, media_type, size_bytes, media_metadata) "
                        "VALUES (:id,:ts,:ts,:project,'video','lesson.mp4','video/mp4',10,'{}')"),
                   dict(id=source, ts=ts, project=project))
        db.execute(text("INSERT INTO processing_jobs (id,created_at,updated_at,project_id,source_id,kind,status,finished_at) "
                        "VALUES (:id,:ts,:ts,:project,:source,'ingest','succeeded',:ts)"),
                   dict(id=job, ts=ts, project=project, source=source))
    command.upgrade(migration, "head")
    with engine.connect() as db:
        assert db.execute(text("SELECT status, stage, progress FROM processing_jobs")).one() == ("succeeded", "complete", 100)
        assert db.scalar(text("SELECT count(*) FROM sources")) == 1
    command.downgrade(migration, "0001_foundation")
    with engine.connect() as db:
        assert db.scalar(text("SELECT count(*) FROM processing_jobs")) == 1
    engine.dispose()
