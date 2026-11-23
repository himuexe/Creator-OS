# Setup and operations

## Existing Windows workspace

The prepared environment has a project virtual environment, frontend dependencies, FFmpeg/FFprobe 9.1, and a local PostgreSQL 17.12 cluster. Run PowerShell commands at the repository root.

```powershell
.\.local\pgsql\bin\pg_isready.exe -h 127.0.0.1 -p 55432
.\.local\pgsql\bin\pg_ctl.exe status -D .local/pgdata
```

If the database is stopped, run `.\.local\pgsql\bin\pg_ctl.exe start -w -D .local/pgdata -l .local/postgres.log`. If the studio is stopped, run `.\.venv\Scripts\python.exe scripts/dev.py`. The launcher reads the user-restricted connection settings in `.local/database.env` and discovers the workspace FFprobe binary. The prepared app and test databases have separate credentials.

Open the [studio](http://127.0.0.1:5173/) and [API schema](http://127.0.0.1:5173/api/v1/openapi.json). The native API also listens on loopback port 8000. Vite forwards `/api` to that server. Health at `/api/v1/health` checks that the migrated workspace exists.

Stop just the studio and API with `.\.venv\Scripts\python.exe scripts/dev.py --stop`. To stop their database afterward, run `.\.local\pgsql\bin\pg_ctl.exe stop -w -D .local/pgdata -m fast`. The SQL data and original files stay on disk. For the background launch used during acceptance, startup and runtime messages are in `.local/studio-output.log` and `.local/studio-errors.log`.

## Fresh checkout with Compose

Use Docker Engine with the Compose plugin, or Docker Desktop configured for Linux containers. Python 3 is used once to generate the password file. Alternatively, copy `.env.example` to `.env` and set both password values to independent random URL-safe strings.

```sh
python scripts/init-env.py
docker compose config --quiet
docker compose up --build -d --wait
docker compose ps
```

The default browser address is [127.0.0.1:5173](http://127.0.0.1:5173/). The initial PostgreSQL entrypoint creates an application role with migration rights in the application schema. The API waits for PostgreSQL, runs migrations and signals readiness before the frontend starts. The Redis container has its own PING health check. Source admission works independently of Redis. Bindings expose only the frontend on loopback.

Use `docker compose logs backend frontend` for startup diagnostics and `docker compose stop` to pause services. Named volumes `database`, `sources` and `broker` preserve state. Database initialization scripts and initial passwords apply on the first start with a new database volume. Change existing database credentials through PostgreSQL and update the environment together.

## Fresh native development environment

Use CPython 3.12 or 3.14, Node 24 LTS with npm, and FFmpeg with FFprobe. The prepared Windows run used Python 3.14.6 and Node 24.16.0. Obtain native PostgreSQL from the platform's supported packages or the EDB Windows archive. A CPU is sufficient for this milestone. [PostgreSQL downloads](https://www.postgresql.org/download/) · [FFmpeg downloads](https://ffmpeg.org/download.html)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-test.txt
npm.cmd ci --prefix frontend
```

On POSIX systems use `.venv/bin/python` and `npm`. If a WindowsApps Python alias is unavailable, use the installed interpreter's full path for the first command.

Supply a private PostgreSQL database and a login role with connect and schema creation rights in its database. Set `DATABASE_URL` in your shell to the SQLAlchemy connection string with driver `postgresql+psycopg`. The launcher also accepts a local `.local/database.env` containing a `DATABASE_URL=...` line. Keep that file private. Set `FFPROBE_BIN` if the executable is outside PATH. Then start `python scripts/dev.py` with the virtual-environment interpreter. For an isolated SQLite studio, run `python scripts/dev.py --sqlite` with that same interpreter. Both modes retain data across restarts.

| Setting | Default or purpose |
| --- | --- |
| `DATABASE_URL` | Native database connection. The launcher selects an external connection, local database file of settings, or explicit SQLite mode. Compose supplies this value. |
| `STORAGE_ROOT` | Private root for staging and original files. Compose mounts `/app/storage`. Native startup selects a directory under `.local` for the chosen mode. |
| `FFPROBE_BIN` | FFprobe executable for the API. |
| `MAX_VIDEO_BYTES` | 536870912 (512 MiB) per video. Accepted containers are MP4, MOV, WebM and MKV. Browser playback depends on codec support. |
| `MAX_SCRIPT_BYTES` | 1048576 (1 MiB) per pasted or uploaded UTF-8 script. File extensions are `.txt` and `.md`. |
| `STUDIO_PORT` | Compose frontend port, default 5173. Native startup uses 5173 and 8000. |

## Verification

In the prepared Windows workspace, use the following commands to exercise real media. On a fresh checkout put FFmpeg and FFprobe on PATH or set their paths to your local build.

```powershell
$mediaDir = (Resolve-Path '.local/media/ffmpeg-9.1-essentials_build/bin').Path
$env:FFMPEG_BIN = Join-Path $mediaDir 'ffmpeg.exe'
$env:FFPROBE_BIN = Join-Path $mediaDir 'ffprobe.exe'
.\.venv\Scripts\python.exe -m pytest -q tests
npm.cmd run build --prefix frontend
```

The Python suite uses temporary SQLite databases by default. To also test PostgreSQL, point `TEST_DATABASE_URL` at a **dedicated test database** whose role can create schemas. Each case runs Alembic in a unique schema and drops that schema at teardown. On the prepared host:

```powershell
$env:TEST_DATABASE_URL = ((Get-Content .local/database-test.env | Where-Object { $_ -like 'DATABASE_URL=*' }) -split '=', 2)[1]
.\.venv\Scripts\python.exe -m pytest -q tests
Remove-Item Env:TEST_DATABASE_URL
```

With the studio running and Chrome, Edge or Chromium available, run `npm.cmd run test:e2e --prefix frontend`. The test uses FFmpeg to generate a synthetic video. An existing browser-playable fixture can be supplied with `CREATOROS_TEST_VIDEO`. Set `CREATOROS_BROWSER` if the browser executable is outside the detected locations. The suite creates unique temporary projects, exercises their UI and removes those records.

## Recovery

Back up PostgreSQL and the private source directory together while writes are paused. Restore the matching pair. A failed upload leaves the draft available for another attempt in its project. A missing FFprobe executable returns a 503 on video intake. Check `FFPROBE_BIN` and retry from the studio. An unsupported or unreadable source returns a validation error without adding a successful ingestion event.

Abrupt host loss can leave an unreferenced file or a staging file. The database and filesystem have separate durability boundaries. With the app stopped, compare server-generated source IDs to a database backup before removing any unreachable files. A missing source referenced by a live row returns 410 and can be restored from the matching backup.
