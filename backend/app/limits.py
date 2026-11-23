from urllib.parse import urlsplit

from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.formparsers import MultiPartException
from starlette.responses import JSONResponse


BODY_LIMIT_ERROR = "The request exceeds the configured size limit."
ENVELOPE_BYTES = 65536


def exceeds_declared_limit(headers, limit):
    length = headers.get("content-length")
    return length is not None and (not length.isascii() or not length.isdecimal() or len(length) > 19 or int(length) > limit)


class LocalRequestPolicy:
    """Bound request bodies before the multipart parser can spool them to disk."""

    def __init__(self, app, config):
        self.app = app
        self.config = config

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = Headers(scope=scope)
        allowed_hosts = {"127.0.0.1", "localhost", "::1", "backend"}
        try:
            host = urlsplit("//" + headers.get("host", "")).hostname
            origin_header = headers.get("origin")
            origin = urlsplit(origin_header) if origin_header else None
        except ValueError:
            return await JSONResponse({"detail": "Invalid host."}, 400)(scope, receive, send)
        if host not in allowed_hosts:
            return await JSONResponse({"detail": "Unknown host."}, 400)(scope, receive, send)
        if scope["method"] not in {"POST", "PATCH", "DELETE", "PUT"}:
            return await self.app(scope, receive, send)
        if headers.get("sec-fetch-site") == "cross-site" or (
            origin and (origin.scheme not in {"http", "https"} or origin.hostname not in allowed_hosts)
        ):
            return await JSONResponse({"detail": "Use the local workspace to make changes."}, 403)(scope, receive, send)
        # Multipart headers and JSON Unicode escaping also consume transport bytes.
        limit = ENVELOPE_BYTES
        if scope["path"].endswith("/sources"):
            limit += max(self.config.max_video_bytes, self.config.max_script_bytes)
        elif scope["path"].endswith("/scripts"):
            limit += self.config.max_script_bytes * 6
        if exceeds_declared_limit(headers, limit):
            return await JSONResponse({"detail": BODY_LIMIT_ERROR}, 413)(scope, receive, send)
        # The upload endpoint narrows this budget to its project's workflow before parsing the form.
        state = scope.setdefault("state", {})
        state["body_limit"] = limit
        size = 0

        async def limited_receive():
            nonlocal size
            chunk = await receive()
            size += len(chunk.get("body", b""))
            if size > state["body_limit"]:
                if headers.get("content-type", "").lower().startswith("multipart/form-data"):
                    # This exception tells Starlette to close already-spooled file handles.
                    raise MultiPartException(BODY_LIMIT_ERROR)
                raise HTTPException(413, BODY_LIMIT_ERROR)
            return chunk

        await self.app(scope, limited_receive, send)
