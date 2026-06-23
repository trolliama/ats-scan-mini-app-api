import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from core import config
from core.logger import get_logger
from core.services.scan_service import process_scan, recover_incomplete_scans
from infra.db.engine import create_db_engine, get_session_factory, init_db
from infra.http.exception_handlers import register_exception_handlers
from infra.http.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    log = get_logger("app")
    engine = create_db_engine(config.get_settings().sqlite_path)
    app.state.engine = engine
    session_factory = get_session_factory(engine)
    app.state.session_factory = session_factory
    init_db(engine)

    scan_ids = recover_incomplete_scans(session_factory)
    if scan_ids:
        log.info("recovering_incomplete_scans", count=len(scan_ids))
        for scan_id in scan_ids:
            asyncio.create_task(
                asyncio.to_thread(process_scan, scan_id, session_factory)
            )
    else:
        log.info("no_incomplete_scans_to_recover")

    yield

    engine.dispose()


def get_app() -> FastAPI:
    lifespan_ctx = (
        None if config.get_settings().skip_app_lifespan else lifespan
    )
    app = FastAPI(lifespan=lifespan_ctx)
    register_exception_handlers(app)
    app.include_router(router)
    return app
