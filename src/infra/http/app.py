from contextlib import asynccontextmanager

from fastapi import FastAPI

from core.config import settings
from infra.db.engine import create_db_engine, get_session_factory, init_db
from infra.http.exception_handlers import register_exception_handlers
from infra.http.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = create_db_engine(settings.sqlite_path)
    app.state.engine = engine
    app.state.session_factory = get_session_factory(engine)
    init_db(engine)

    # Deferred: recover_incomplete_scans + enqueue process_scan

    yield

    engine.dispose()


def get_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    register_exception_handlers(app)
    app.include_router(router)
    return app
