# CreatorOS foundation

The first release is a local, single-creator production workspace. A creator opens a project, chooses the recorded-video or written-script workflow, and stores original material. A project with a validated source can enter the next production milestone. Original sources are distinct from future generated assets.

## Runtime

React and TypeScript serve the dashboard, project list and project studio. A single same-origin HTTP API connects them to a FastAPI modular monolith. Vite proxies requests in development. The production web container serves the frontend build and forwards API requests. PostgreSQL stores relational state. A private local storage directory holds original bytes under generated identifiers. Only workspace-scoped API routes serve source content. Alembic establishes the database schema before the API starts.

FFprobe reads uploaded video from a controlled local staging area using a fixed argument list, a timeout and restricted protocols. The admission path checks that media really contains video and records the observed properties. Script ingestion accepts pasted text or a UTF-8 text or Markdown file. Successful ingestion, the project state and processing history belong to the same database operation. A failed submission should leave the project usable for another attempt.

## Deployment boundary

Bind the public web port to loopback. Keep the API, database and Redis on the private Compose network. Native development also uses loopback. The application resolves one local workspace on the server. Before allowing untrusted network access, introduce authenticated identity, workspace membership, per-workspace quotas and TLS. PostgreSQL owns project state; the filesystem and database need coordinated backups.

## Incremental processing

Milestone 1 records completed source intake. Its media inspection is bounded and runs outside the asynchronous event loop. Introduce Celery workers against the Redis broker with the first expensive operation in Milestone 2. Their contract will carry source and job IDs, support retries and prevent duplicate outputs. Semantic analysis returns typed suggestions linked to source coordinates. Rendering requires creator approval of a segment. Publishing will require separate explicit authorization and platform credentials.

The planned interfaces for transcription, structured LLM output, voice and distribution belong behind backend services. Their model dependencies, credentials and cost are unnecessary for Milestone 1. Source files and model outputs must always be treated as untrusted data.
