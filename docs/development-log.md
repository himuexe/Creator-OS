# Development log

## 2026-11-23 · Milestone 0

**Result.** The machine can run the personal studio, PostgreSQL and CPU-based media inspection natively. The repository already had Git history, its name and an MIT license. Implementation extended that checkout.

| Check | Evidence and outcome |
| --- | --- |
| Host and repository | Ran `git status --short --branch`, `git ls-files`, `Get-Command`, `Get-PSDrive`, hardware inventory via `Get-CimInstance`, runtime version checks and `wsl --list --verbose`. The [audit](environment-audit.md) records the hardware and initial tool inventory. |
| Upstream review | Reviewed FFmpeg/FFprobe, FFmpeg Skill, Postiz and VoiceStudio. The [research notes](integration-research.md) link releases, documentation, licenses and API contracts. Postiz and VoiceStudio are candidates for later integrations. |
| Decisions and files | Created the [architecture](architecture.md), [decision record](decisions/0001-foundation.md) and [roadmap](development-roadmap.md). Selected PostgreSQL and local source storage. Reserved Redis-backed workers for expensive production jobs. |

The missing Docker engine and WSL installation led to a native verification path. The Compose deployment definition retains the preferred stack. No model downloads, provider keys or paid services were needed.

## 2026-11-23 · Milestone 1

**Result.** A creator can create a project, attach a recorded video, paste a script or upload text/Markdown. Both studios persist projects and originals, display source previews, and share a dashboard and ingestion history. A failed submission keeps the project available for retry.

### Implementation and files

| Area | Changes |
| --- | --- |
| Frontend | `frontend/src/` contains overview, search/filter, project forms, detail views, API client, upload progress, script/video previews and responsive navigation. `frontend/tests/studio.mjs` exercises the actual browser UI. The frontend includes Vite, TypeScript and Tailwind configuration, its lockfile and a multi-stage Dockerfile with Nginx. |
| API and storage | `backend/app/` contains versioned routes, typed requests/responses, workspace resolution, upload limits, transactional ingestion, FFprobe inspection and private range-enabled content serving. |
| Schema | `backend/migrations/` and `backend/alembic.ini` create the workspace, project, source and processing history tables. The [database design](database-design.md) and [API specification](api-specification.md) describe the contracts. |
| Startup | `docker-compose.yml`, the two service Dockerfiles, `.env.example`, `.gitignore`, `scripts/init-db.sql`, `scripts/init-env.py` and `scripts/dev.py` provide container and native entry points. `README.md` and the [setup guide](setup-guide.md) document them. |
| Tests | `tests/conftest.py` isolates the data and generates synthetic media. `tests/test_foundation.py` covers API, schema, storage and FFprobe integration. Runtime and test dependencies are in the backend requirements files. |

### Installed and configured

- Native runtime used CPython 3.14.6, Node 24.16.0 and npm 11.13.0. Pinned backend dependencies include FastAPI 0.165.0, Pydantic 2.14.4, SQLAlchemy 2.0.58, Alembic 1.20.1, Psycopg 3.3.9, Uvicorn 0.54.0 and python-multipart 0.0.34. The resolved browser stack includes React 19.3.1, TypeScript 5.9.3, Vite 8.3.8, Tailwind 4.3.5 and Playwright Core 1.65.1.
- PostgreSQL 17.12 came from the EDB Windows x64 binary archive. Verified the server executable's EnterpriseDB signature. Initialized a UTF-8 cluster with SCRAM authentication and loopback port 55432. The app and test database logins were checked separately after a database restart. Credentials are kept in ignored, access-restricted files. [Official Windows distribution](https://www.postgresql.org/download/windows/)
- FFmpeg and FFprobe 9.1 came from the Windows essentials release. The initial download timed out. The release mirror yielded the archive with SHA-256 `835b9a733445ba7a56a37a26cf7bde84e2f3ce7da2a8ec984276bb2abb1b922c`, matching the publisher's checksum. Executables live under `.local/media/`. [Windows builds and checksums](https://www.gyan.dev/ffmpeg/builds/)
- Docker Compose v2.39.4 was used as a standalone configuration validator. The definition includes the `db`, `redis`, `backend` and `frontend` services. Only the web port is published.

### Commands and verification

Commands below use the project virtual environment and repository root unless otherwise indicated. The setup guide includes the Windows paths and per-test environment settings.

| Command or check | Observed result |
| --- | --- |
| `python -m pip install -r backend/requirements-test.txt` and `python -m pip check` | Native packages installed. No broken requirements. |
| `python scripts/init-env.py` and `docker-compose config --quiet` with the official standalone CLI | Generated local Compose credentials and validated the config. `config --services` returned all four services. |
| Native `initdb`, `pg_ctl`, `pg_isready` and SQL connection checks | PostgreSQL accepted authenticated connections on loopback. Application and test roles are scoped to their own databases. |
| `python scripts/dev.py` | Applied `alembic upgrade head` and launched Uvicorn and Vite. The dashboard, Swagger and database-backed health endpoint returned HTTP 200. |
| `python -m pytest -q tests` | **16 passed on SQLite**, with synthetic media and FFprobe enabled. |
| `TEST_DATABASE_URL` set to the isolated PostgreSQL database, then `python -m pytest -q tests` | **16 passed on PostgreSQL 17.12**. These are the same 16 cases exercised on the deployment dialect. |
| `npm run build` in `frontend/` | TypeScript checking and Vite production compilation passed. |
| `npm run test:e2e` against the dev server | Chrome passed script creation/reload, project editing, Markdown upload, invalid file replacement, corrupt-video rejection, retry, playable video and history, filtering, mobile navigation and project deletion. The test observed no uncaught page errors. |
| Same browser suite against `vite preview` on port 4173 | Passed against the production frontend bundle and the live API. The temporary preview server stopped after the check. |
| Independent HTTP and SQL acceptance check | Posted two projects and three sources through the frontend proxy. A direct PostgreSQL query verified a source/job pair for each original and the active Alembic revision. Restarted the application, retrieved all three originals and checked their hashes. Verified HTTP 206 and exact bytes for a video range read. Removed the temporary acceptance projects. |

The browser fixture was a synthetic H.264/AAC MP4, 320 × 180, 24 fps, two seconds, with one audio stream. Browser-decoded dimensions and duration agreed with FFprobe. The Python suite also generated and inspected an independent MPEG-4/AAC test file. Failure coverage includes invalid UTF-8, blank or oversized sources, unsupported file types, interrupted commits, a lost commit acknowledgement, missing FFprobe, multipart limits and workspace boundaries.

### Verification limits and next milestone

The host has no Docker engine or WSL. Image builds, the Nginx container, the Postgres container entrypoint and the Redis container still need a full `docker compose up --build -d --wait` smoke test on a Docker-capable host. Native PostgreSQL, API, source storage, Chrome and the frontend build were exercised directly. Redis has no runtime consumer in this milestone.

The current deployment assumes one trusted local creator. Asset generation, transcript/clip editing, approvals and publishing are future milestones. The next implementation gate is Milestone 2: a durable worker, timestamped transcription, and source-grounded clip suggestions that can be edited and previewed.
