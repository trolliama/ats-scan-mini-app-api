from collections.abc import Generator

from fastapi import Header, HTTPException, Request

from core.config import settings
from infra.db.unit_of_work import UoWContext, unit_of_work


def get_uow(request: Request) -> Generator[UoWContext, None, None]:
    factory = request.app.state.session_factory
    with unit_of_work(factory) as uow:
        yield uow


def verify_api_key(x_api_key: str = Header(alias="X-API-Key")) -> None:
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
