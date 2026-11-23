from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from .api import router
from .analysis import router as analysis_router
from .config import Settings
from .db import make_engine, session_factory
from .limits import LocalRequestPolicy


def create_app(config: Settings | None = None):
    config = config or Settings.from_env()
    engine = make_engine(config.database_url)

    @asynccontextmanager
    async def lifespan(app):
        yield
        engine.dispose()

    app = FastAPI(title="CreatorOS", version="0.2.0", docs_url="/api/v1/docs",
                  openapi_url="/api/v1/openapi.json", redoc_url=None,
                  swagger_ui_oauth2_redirect_url=None, lifespan=lifespan)
    app.state.config = config
    app.state.sessions = session_factory(engine)
    app.add_middleware(LocalRequestPolicy, config=config)
    app.include_router(router)
    app.include_router(analysis_router)

    @app.exception_handler(SQLAlchemyError)
    def database_error(request: Request, exc: SQLAlchemyError):
        logging.getLogger(__name__).exception("Database operation failed.")
        return JSONResponse({"detail": "The workspace database is unavailable. Check its connection and migrations."}, 503)

    @app.exception_handler(OSError)
    def storage_error(request: Request, exc: OSError):
        logging.getLogger(__name__).exception("Source storage operation failed.")
        return JSONResponse({"detail": "Source storage is unavailable. Check free space and permissions."}, 503)

    return app


app = create_app()
