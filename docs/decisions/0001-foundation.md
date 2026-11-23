# 0001. Local single-creator modular monolith

Accepted on 2026-11-23 for Milestone 1.

- Use the requested React/TypeScript/Vite/Tailwind and FastAPI/Pydantic/SQLAlchemy stack. Use Alembic for migrations, PostgreSQL for persisted deployment data and private local files for source bytes. This keeps the first workflows on one transaction and access-control boundary.
- Provide a native application launch alongside Docker Compose. This Windows host has no Docker engine or WSL installation. A native PostgreSQL cluster exercises the same database dialect without changing system services. SQLite is available for isolated tests and an explicitly selected lightweight development mode.
- Validate videos with FFprobe at intake. Restrict FFmpeg to backend-owned operations. Defer audio extraction, model installation and rendering until the relevant milestones can be tested against actual media.
- Include Redis in the deployment topology. Introduce the Celery dependency and background workers with transcription. A bounded admission check suffices for the foundation and avoids running idle development workers.
- Use the shared project/source/ingestion-history model for video and script. Delay generated-asset versions, publishing accounts, brand profiles and multi-user tables until the associated workflows ship.
- Keep Postiz and VoiceStudio independent of the foundation. Revisit external APIs, deployment constraints and licenses at the relevant milestones.
