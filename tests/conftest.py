import os
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from app.config import Settings
from app.main import create_app


@pytest.fixture
def database_url(tmp_path):
    postgres = os.environ.get("TEST_DATABASE_URL")
    if not postgres:
        yield "sqlite:///" + (tmp_path / "workspace.db").as_posix()
        return
    # Test tables live in a fresh owned schema even on an existing local DB.
    admin = create_engine(postgres)
    schema = "test_" + uuid4().hex
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = make_url(postgres).update_query_dict({"options": f"-csearch_path={schema}"})
    try:
        yield url.render_as_string(hide_password=False)
    finally:
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def config(tmp_path, database_url):
    migration = Config(str(BACKEND / "alembic.ini"))
    migration.attributes["database_url"] = database_url
    command.upgrade(migration, "head")
    return Settings(database_url, tmp_path / "storage", os.environ.get("FFPROBE_BIN", "ffprobe"),
                    max_script_bytes=1024, max_video_bytes=1024 * 1024)


@pytest.fixture
def client(config):
    with TestClient(create_app(config), base_url="http://localhost") as test_client:
        yield test_client


@pytest.fixture(scope="session")
def video(tmp_path_factory):
    encoder = shutil.which(os.environ.get("FFMPEG_BIN", "ffmpeg"))
    probe = shutil.which(os.environ.get("FFPROBE_BIN", "ffprobe"))
    if not encoder or not probe:
        pytest.skip("Install FFmpeg/FFprobe or set FFMPEG_BIN and FFPROBE_BIN to run the real media check.")
    path = tmp_path_factory.mktemp("media") / "lecture.mp4"
    subprocess.run([
        encoder, "-v", "error", "-nostdin", "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=8",
        "-f", "lavfi", "-i", "sine=frequency=440", "-t", "1", "-c:v", "mpeg4", "-c:a", "aac",
        str(path),
    ], check=True, timeout=30)
    return path
