from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from core.exceptions import DuplicateScanError, ScanNotFound


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DuplicateScanError)
    async def duplicate_scan_handler(
        _request: Request, _exc: DuplicateScanError
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": "Scan already exists"})

    @app.exception_handler(ScanNotFound)
    async def scan_not_found_handler(
        _request: Request, _exc: ScanNotFound
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": "Scan not found"})
