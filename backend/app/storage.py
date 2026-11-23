from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import BinaryIO
from uuid import UUID

from fastapi import HTTPException


class LocalStorage:
    """Only server-generated project and source IDs are used in storage paths."""

    def __init__(self, root: Path):
        self.root = root

    def location(self, project_id: UUID, source_id: UUID):
        return self.root / "sources" / project_id.hex / source_id.hex

    @contextmanager
    def stage(self, stream: BinaryIO, limit: int):
        staging = self.root / "staging"
        staging.mkdir(exist_ok=True, parents=True)
        with NamedTemporaryFile(dir=staging, delete=False) as output:
            temporary = Path(output.name)
        try:
            size = 0
            with temporary.open("wb") as output:
                while chunk := stream.read(1024 * 1024):
                    size += len(chunk)
                    if size > limit:
                        raise HTTPException(413, "The source exceeds the configured file size limit.")
                    output.write(chunk)
            if not size:
                raise HTTPException(422, "An empty file cannot be used as a source.")
            yield temporary, size
        finally:
            temporary.unlink(missing_ok=True)
