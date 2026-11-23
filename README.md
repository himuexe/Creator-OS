# CreatorOS

CreatorOS is a local production studio for educational creators. Milestone 1 takes a recorded video or written script into a persistent project, verifies its source, and makes the original available for review.

**[Open the local studio](http://127.0.0.1:5173/) · [Open the API reference](http://127.0.0.1:5173/api/v1/docs)**

1. Choose **Video studio** or **Script studio** and create a project.
2. Upload a recording, paste a script, or attach a UTF-8 text or Markdown file.
3. Open the source preview and its ingestion history. For video, inspect duration, dimensions, frame rate and audio stream count.

The overview summarizes real projects, sources and processing activity. Transcription, clip selection, rendering, narration, editorial approval and distribution follow in later milestones.

## Run on the provisioned Windows workspace

Run commands from the repository root. If PostgreSQL is stopped, start it first.

```powershell
.\.local\pgsql\bin\pg_ctl.exe status -D .local/pgdata
# Run only when the status reports that the server is stopped.
.\.local\pgsql\bin\pg_ctl.exe start -w -D .local/pgdata -l .local/postgres.log
```

```powershell
.\.venv\Scripts\python.exe scripts/dev.py
```

The launcher applies Alembic migrations and starts FastAPI and Vite. To stop those two processes, press Ctrl+C in the launcher or run `.\.venv\Scripts\python.exe scripts/dev.py --stop` in a second terminal. The PostgreSQL cluster persists independently.

## Run from a fresh checkout with Docker

```sh
python scripts/init-env.py
docker compose up --build -d --wait
```

Open the studio at port 5173. The Compose definition includes PostgreSQL, Redis, the API and the frontend. The native deployment was tested end to end on Windows. The Compose configuration passed validation; running the containers requires a Docker engine.

## Documentation

- [Setup, configuration, testing and recovery](docs/setup-guide.md)
- [Development log and acceptance results](docs/development-log.md)
- [Architecture](docs/architecture.md) and [initial decisions](docs/decisions/0001-foundation.md)
- [Database design](docs/database-design.md) and [API specification](docs/api-specification.md)
- [Environment audit](docs/environment-audit.md), [integration research](docs/integration-research.md) and [milestone roadmap](docs/development-roadmap.md)
