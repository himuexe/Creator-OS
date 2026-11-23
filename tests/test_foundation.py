from dataclasses import replace
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.main import create_app
from app.models import ProcessingJob, Project, Source, Workspace


def project(client, workflow="script"):
    created = client.post("/api/v1/projects", json={"name": "  Educational video  ", "workflow": workflow})
    assert created.status_code == 201, created.text
    return created.json()


def test_project_lifecycle(client, config):
    assert client.get("/api/v1/health").json()["status"] == "ok"
    assert client.get("/api/v1/openapi.json").json()["info"]["title"] == "CreatorOS"
    created = project(client)
    path = "/api/v1/projects/" + created["id"]
    assert created["status"] == "draft" and created["source_count"] == 0
    assert created["created_at"].endswith("Z")
    assert created["name"] == "Educational video"
    assert client.patch(path, json={"description": "A lesson"}).status_code == 200
    # Start a new ASGI app and connection pool against the same database.
    with TestClient(create_app(config), base_url="http://localhost") as restarted:
        assert restarted.get(path).json()["description"] == "A lesson"
        assert restarted.get("/api/v1/projects").json()[0]["id"] == created["id"]
    assert client.delete(path).status_code == 204
    assert client.get(path).status_code == 404


def test_script_input_and_file_upload(client, config):
    created = project(client)
    path = "/api/v1/projects/" + created["id"]
    original = "  What makes a good example?\nकदम १.\n"
    direct = client.post(path + "/scripts", json={"text": original})
    assert direct.status_code == 201, direct.text
    source = direct.json()
    assert source["size_bytes"] == len(original.encode())
    assert source["metadata"]["word_count"] == len(original.split())
    assert client.get(source["content_url"]).content == original.encode()
    uploaded = client.post(path + "/sources", files={"file": ("lesson.md", b"# Welcome\nA lesson.", "text/markdown")})
    assert uploaded.status_code == 201, uploaded.text
    assert client.get(path + "/sources").json()[0]["filename"] == "lesson.md"
    assert client.get(path).json()["source_count"] == 2
    assert client.get(path).json()["status"] == "ready"
    jobs = client.get(path + "/jobs").json()
    assert len(jobs) == 2 and jobs == client.get("/api/v1/jobs").json()
    assert {j["source_id"] for j in jobs} == {source["id"], uploaded.json()["id"]}
    assert all(j["kind"] == "ingest" and j["status"] == "succeeded" for j in jobs)
    assert client.delete(path).status_code == 204
    assert client.get(source["content_url"]).status_code == 404
    assert not list((config.storage_root / "sources").rglob("*"))
    with client.app.state.sessions() as db:
        assert db.scalar(select(func.count(Source.id))) == db.scalar(select(func.count(ProcessingJob.id))) == 0


@pytest.mark.parametrize(("filename", "contents", "status"), [
    ("draft.txt", b"", 422), ("draft.md", b"  \n ", 422), ("draft.txt", b"abc\x00", 422),
    ("draft.txt", b"\xff", 422), ("draft.exe", b"content", 415), ("draft.txt", b"x" * 1025, 413),
])
def test_invalid_uploads_leave_no_partial_sources(client, config, filename, contents, status):
    path = "/api/v1/projects/" + project(client)["id"]
    response = client.post(path + "/sources", files={"file": (filename, contents)})
    assert response.status_code == status, response.text
    assert client.get(path).json()["status"] == "draft"
    assert client.get(path + "/jobs").json() == []
    assert not [p for p in config.storage_root.rglob("*") if p.is_file()]


def test_video_upload_and_range_preview(client, video):
    path = "/api/v1/projects/" + project(client, "video")["id"]
    data = video.read_bytes()
    result = client.post(path + "/sources", files={"file": (video.name, data, "video/mp4")})
    assert result.status_code == 201, result.text
    source = result.json()
    meta = source["metadata"]
    assert (meta["width"], meta["height"], meta["frame_rate"], meta["audio_streams"]) == (160, 90, 8, 1)
    assert meta["duration_seconds"] == pytest.approx(1, abs=0.15)
    assert client.get(source["content_url"]).content == data
    preview = client.get(source["content_url"], headers={"Range": "bytes=0-9"})
    assert preview.status_code == 206 and preview.content == data[:10]
    assert preview.headers["Cross-Origin-Resource-Policy"] == "same-origin"
    assert client.post(path + "/sources", files={"file": ("broken.mp4", b"Just a filename")}).status_code == 422
    assert len(client.get(path + "/sources").json()) == 1


def test_unavailable_probe_leaves_no_source(config):
    with TestClient(create_app(replace(config, ffprobe_bin="missing-creatoros-ffprobe")), base_url="http://localhost") as client:
        path = "/api/v1/projects/" + project(client, "video")["id"]
        response = client.post(path + "/sources", files={"file": ("clip.mp4", b"bytes")})
        assert response.status_code == 503 and "FFprobe" in response.json()["detail"]
        assert client.get(path + "/sources").json() == []


def test_safe_names_validation_and_request_limits(client):
    path = "/api/v1/projects/" + project(client)["id"]
    source = client.post(path + "/scripts", json={"text": "hello", "filename": "../../notes.txt"}).json()
    assert source["filename"] == "notes.txt" and source["content_url"].startswith("/api/v1/sources/")
    assert client.post(path + "/scripts", json={"text": "é" * 513}).status_code == 413
    assert client.post(path + "/scripts", json={"text": " "}).status_code == 422
    assert client.post(path + "/scripts", json={"text": "x" * 90000}).status_code == 413
    assert client.patch(path, json={"name": "  "}).status_code == 422
    assert client.patch(path, json={"name": None}).status_code == 422
    video_path = "/api/v1/projects/" + project(client, "video")["id"]
    assert client.post(video_path + "/scripts", json={"text": "text"}).status_code == 422
    assert client.post(path + "/scripts", json={"text": "Hello"}, headers={"Origin": "https://example.org"}).status_code == 403
    assert client.get(path, headers={"Host": "example.org"}).status_code == 400


def test_workspace_isolation(client):
    with client.app.state.sessions() as db:
        other = Workspace(id=uuid4(), name="Other workspace")
        db.add(other)
        db.flush()
        p = Project(id=uuid4(), workspace_id=other.id, name="Private", workflow="script")
        db.add(p)
        db.flush()
        s = Source(id=uuid4(), project_id=p.id, kind="script", filename="private.txt", media_type="text/plain", size_bytes=5, facts={})
        db.add(s)
        db.flush()
        db.add(ProcessingJob(project_id=p.id, source_id=s.id))
        db.commit()
        path, content = "/api/v1/projects/" + str(p.id), s.content_url
    assert client.get("/api/v1/projects").json() == client.get("/api/v1/jobs").json() == []
    assert client.get(path).status_code == client.get(content).status_code == 404
    assert client.post(path + "/scripts", json={"text": "unavailable"}).status_code == 404
    assert client.delete(path).status_code == 404


def test_chunked_and_declared_multipart_budgets(client):
    path = "/api/v1/projects/" + project(client)["id"] + "/sources"
    # Far smaller than the video limit and larger than the complete script transport budget.
    headers = {"Content-Type": "multipart/form-data; boundary=creator"}
    body = [b'--creator\r\nContent-Disposition: form-data; name="file"; filename="script.txt"\r\n\r\n',
            b"A" * 70000, b"\r\n--creator--\r\n"]
    assert client.post(path, headers=headers, content=b"".join(body)).status_code == 413
    assert client.post(path, headers=headers, content=iter(body)).status_code == 413
    assert client.get(path).json() == []
    duplicate = [("file", ("a.txt", b"hello")), ("file", ("b.txt", b"hello"))]
    assert client.post(path, files=duplicate).status_code == 400


def test_failed_database_commit_cleans_staged_source(client, config, monkeypatch):
    path = "/api/v1/projects/" + project(client)["id"]

    def failed_commit(session):
        raise SQLAlchemyError("Injected failure")

    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", failed_commit)
        response = client.post(path + "/scripts", json={"text": "source"})
        assert response.status_code == 503
    assert client.get(path).json()["status"] == "draft"
    assert client.get(path + "/jobs").json() == client.get(path + "/sources").json() == []
    assert not [p for p in config.storage_root.rglob("*") if p.is_file()]


def test_failed_project_delete_keeps_files(client, monkeypatch):
    path = "/api/v1/projects/" + project(client)["id"]
    content_url = client.post(path + "/scripts", json={"text": "keep me"}).json()["content_url"]

    def failed_commit(session):
        raise SQLAlchemyError("Injected failure")

    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", failed_commit)
        assert client.delete(path).status_code == 503
    assert client.get(path).json()["source_count"] == 1
    assert client.get(content_url).text == "keep me"


def test_lost_commit_acknowledgement_keeps_original(client, monkeypatch):
    path = "/api/v1/projects/" + project(client)["id"]
    commit = Session.commit

    def lost_acknowledgement(session):
        commit(session)
        raise SQLAlchemyError("Lost acknowledgement after durable commit")

    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", lost_acknowledgement)
        accepted = client.post(path + "/scripts", json={"text": "Keep the committed original."})
    assert accepted.status_code == 201
    assert client.get(accepted.json()["content_url"]).text == "Keep the committed original."
    assert len(client.get(path + "/jobs").json()) == 1
