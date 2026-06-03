from sqlalchemy.orm import Session, sessionmaker

from infra.http.schemas import CreateScanRequest, CreateScanResponse
from infra.db.unit_of_work import UoWContext


def create_scan(uow: UoWContext, body: CreateScanRequest) -> CreateScanResponse:
    """Deferred: insert pending scan and commit — see .specs/features/ats-scan-worker/design.md."""
    raise NotImplementedError


def process_scan(scan_id: str, session_factory: sessionmaker[Session]) -> None:
    """Deferred: full ATS scan pipeline — see .specs/features/ats-scan-worker/design.md."""
    raise NotImplementedError


def recover_incomplete_scans(session_factory: sessionmaker[Session]) -> list[str]:
    """Deferred: ATS-24 startup recovery — re-enqueue incomplete scans on boot."""
    raise NotImplementedError
