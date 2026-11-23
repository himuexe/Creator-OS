# Development roadmap

| Milestone | Deliverable | Acceptance gate |
| --- | --- | --- |
| 0 · Research | Host audit, four upstream evaluations, architecture and decisions | Establish feasible local execution and document licensing, service boundaries and limitations. |
| 1 · Foundation | Studio, project management, video and script intake, schema, storage and deployment | Create projects through the studio, upload a real video, save a pasted script or Markdown file and retrieve original content after refresh. See the development log for tested environments. |
| 2 · Video intelligence | Audio extraction, replaceable transcription, timestamped segments, structured LLM analysis and editable recommendations | Submit an educational recording, inspect its time-aligned transcript and preview suggestions grounded in complete transcript passages. Validate provider output and source-relative times. |
| 3 · Video production | Human-approved trims, vertical composition, captions, audio normalization and versioned output | Probe and decode an approved 9:16 clip. Check duration, streams, readable subtitles and source provenance. |
| 4 · Script production | Editable scene planning, replaceable optional narration and video assembly | Render a playable educational video from a script and verify its scenes, audio, subtitle timing and metadata. |
| 5 · Creator studio | Asset gallery, transcript/scene editing, regeneration, brand settings and review history | Complete review and regeneration through the UI while preserving previous asset versions. |
| 6 · Distribution | Authorized Postiz API workflow and publication status | Record explicit approval of the asset version, destination and schedule. Reconcile delivery against the authorized account. |

## First work after foundation

Introduce a durable job state machine with bounded retries and cancellation. Benchmark a small faster-whisper CPU/int8 model on a consented educational recording. Record real-time factor, peak memory and transcript accuracy before selecting a default. The 4 GiB GPU needs a separate compatibility and capacity test. Persist ordered transcript segments before enabling clip analysis. Require structured provider responses and retain the original transcript text for editorial review.
