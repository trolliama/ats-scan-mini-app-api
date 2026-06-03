from fastapi import FastAPI


def register_exception_handlers(app: FastAPI) -> None:
    # Deferred: DuplicateScanError → 409
    # Deferred: ScanNotFound → 404
    # Deferred: S3ObjectNotFoundError → 502
    pass
