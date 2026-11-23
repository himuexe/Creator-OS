# CreatorOS v1 API

The studio and the API share an origin. In a running installation, open the [interactive API](http://127.0.0.1:5173/api/v1/docs) or its [machine-readable schema](http://127.0.0.1:5173/api/v1/openapi.json). The personal workspace is selected by the server. Resource IDs are UUIDs.

| Method | Path under `/api/v1` | Operation |
| --- | --- | --- |
| GET | `/health` | Check database readiness and read effective intake limits. |
| POST | `/projects` | Create a draft with `name`, `workflow` (`video` or `script`) and optional `description`. |
| GET | `/projects` | List projects and source counts. |
| GET, PATCH, DELETE | `/projects/{id}` | Read the project, edit its name or description, or delete it with its source data. |
| GET | `/projects/{id}/sources` | List the private source descriptors and content URLs. |
| POST | `/projects/{id}/sources` | Submit one `multipart/form-data` field named `file`. Choose an input compatible with the project's workflow. |
| POST | `/projects/{id}/scripts` | Save UTF-8 script text with JSON fields `text` and optional `filename`. |
| GET | `/sources/{id}/content` | Retrieve the original source for preview or download. |
| GET | `/projects/{id}/jobs` | Read recorded ingestion events. |
| GET | `/jobs` | List ingestion events across the personal workspace for the activity view. |

## Example

```http
POST /api/v1/projects
Content-Type: application/json

{"name":"How a camera sensor works","workflow":"script"}
```

Use the project's returned `id` with `POST /api/v1/projects/{id}/scripts` and the following body.

```json
{"filename":"sensor.md","text":"# Camera sensors\nA photosite measures incoming light during an exposure."}
```

Open the returned source's `content_url` for its bytes. Refresh the project to see `ready` and a source count of one. An invalid upload leaves the project available for another submission. Creation and source attachment use separate requests so a creator can resume a draft. Future transcript, render, review and publishing endpoints will be added when their workers and validation exist.
