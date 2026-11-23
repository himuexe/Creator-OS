from dataclasses import dataclass
import os
from pathlib import Path
from uuid import UUID


# The personal deployment owns this workspace, seeded in the first migration.
PERSONAL_WORKSPACE = UUID("3f4cb678-5474-4fa0-98e0-aab0cf8a2e0e")


@dataclass(frozen=True)
class Settings:
    database_url: str
    storage_root: Path
    ffprobe_bin: str = "ffprobe"
    max_video_bytes: int = 512 * 1024 * 1024
    max_script_bytes: int = 1024 * 1024

    @classmethod
    def from_env(cls):
        config = cls(
            database_url=os.environ.get("DATABASE_URL", "sqlite:///creatoros.db"),
            storage_root=Path(os.environ.get("STORAGE_ROOT", "storage")).resolve(),
            ffprobe_bin=os.environ.get("FFPROBE_BIN", "ffprobe"),
            max_video_bytes=int(os.environ.get("MAX_VIDEO_BYTES", str(cls.max_video_bytes))),
            max_script_bytes=int(os.environ.get("MAX_SCRIPT_BYTES", str(cls.max_script_bytes))),
        )
        if min(config.max_video_bytes, config.max_script_bytes) < 1:
            raise ValueError("Source size limits must be positive.")
        return config
