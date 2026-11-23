# Foundation database

Alembic revision `0001_foundation` creates the tables and seeds one personal workspace. IDs are UUIDs. Application timestamps are UTC and database foreign keys protect parent/child relationships. The native launcher and Compose both apply migrations before serving requests.

| Table | Ownership and contents |
| --- | --- |
| `workspaces` | Identity and display name of the personal workspace. The API resolves it server-side. |
| `projects` | Workspace FK, name, description, immutable workflow, state, timestamps. The initial state is `draft`. Adding a validated source sets it to `ready`. |
| `sources` | Project FK, kind, display filename, byte length, media type, validated metadata. The object's generated ID identifies the stored original. |
| `processing_jobs` | Project and source FKs, operation, completion state and timings. Each accepted source has one successful ingestion record. |

The API computes project source counts from source rows. Two files with the same display name can have independent identities. The database stores references and facts; original media stays in the private source volume. Project deletion cascades to child rows and removes stored project sources.

## Next schema changes

Milestone 2 adds transcripts and timestamped segments keyed to a source, clip candidates, provider/model metadata, job attempts and error details. Milestones 3–5 add versioned assets, render inputs, scenes, brand profiles and review decisions. Publishing will reference the specifically approved asset version. Credentials belong in secret storage. Add user identity and workspace membership before exposing multi-user access. Each extension needs its own Alembic revision and migration test.
