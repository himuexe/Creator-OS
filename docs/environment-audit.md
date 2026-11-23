# Development environment

Inspected on 2026-11-23 in the Windows workspace at `D:\Creator-OS`. The clean Git checkout on `main` initially contained the original MIT license and a project heading. There was no implementation, dependency lock, migration history, or sample media.

| Resource | Observed | Engineering consequence |
| --- | --- | --- |
| OS | Windows 11 Home Single Language, x64, build 26300 | Support PowerShell development and Linux containers. |
| CPU | Ryzen 5 4600H, 6 cores / 12 logical processors | FFprobe admission and short synthetic fixtures fit the host. |
| RAM | 15.36 GiB visible, 6.67 GiB available at inspection | Defer transcription model choice to measured Milestone 2 runs. |
| Storage | D: 484 GiB free, C: 95 GiB free | Keep sources and development state on the workspace drive. |
| GPU | GTX 1650 Ti, about 4 GiB reported VRAM, driver 32.0.16.1091. Integrated AMD Radeon also present | CUDA model compatibility and throughput have yet to be measured. No GPU required for ingestion. |
| Python | CPython 3.14.6 x64, pip 26.1.2 | Use a project virtual environment. WindowsApps aliases were inaccessible from the sandbox; the interpreter under LocalAppData worked. |
| JavaScript | Node 24.16.0, npm 11.13.0 | Use the installed Node runtime and commit the frontend lockfile. |
| Git | 2.54.0.windows.1 | Preserve the existing repository and license. |
| Containers | Docker, Compose, Podman absent from PATH. WSL reports no installation. | Ship Compose and also exercise the app as native processes. |
| Database and broker | PostgreSQL and Redis server binaries absent from PATH at inspection | Use an isolated native PostgreSQL cluster if available. Redis is the Compose broker for future workers. |
| Media | FFmpeg and FFprobe absent from PATH at inspection | Use a workspace-local build or explicit executable paths for validation. |

Inspection used Get-Command, Get-PSDrive, Get-CimInstance, wsl --list --verbose, runtime version checks, git status, and git ls-files. Host availability above describes the initial environment. Executed setup, versions, and verification results are recorded in [the development log](development-log.md).
