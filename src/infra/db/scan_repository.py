from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.exceptions import DuplicateScanError, ScanNotFound
from core.enums import ScanStatus
from core.models import ATSScanResult, ScanCreate, ScanRecord
from infra.db.models import Scan

_INCOMPLETE_SCAN_STATUSES = (ScanStatus.PENDING, ScanStatus.PROCESSING)


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _to_record(scan: Scan) -> ScanRecord:
    result = None
    if scan.result_json is not None:
        result = ATSScanResult.model_validate_json(scan.result_json)
    return ScanRecord(
        id=scan.id,
        session_id=scan.session_id,
        file_key=scan.file_key,
        bucket=scan.bucket,
        original_filename=scan.original_filename,
        status=ScanStatus(scan.status),
        ats_score=scan.ats_score,
        job_title_detected=scan.job_title_detected,
        failure_reason=scan.failure_reason,
        result=result,
        webhook_processing_sent=scan.webhook_processing_sent,
        webhook_terminal_sent=scan.webhook_terminal_sent,
        created_at=scan.created_at,
        updated_at=scan.updated_at,
        started_at=scan.started_at,
        completed_at=scan.completed_at,
    )


class ScanRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def insert_pending(self, record: ScanCreate) -> None:
        now = _utc_now()
        scan = Scan(
            id=str(record.scan_id),
            session_id=str(record.session_id),
            file_key=record.file_key,
            bucket=record.bucket,
            original_filename=record.original_filename,
            status=ScanStatus.PENDING,
            webhook_processing_sent=False,
            webhook_terminal_sent=False,
            created_at=now,
            updated_at=now,
        )
        self._session.add(scan)
        try:
            self._session.flush()
        except IntegrityError:
            self._session.rollback()
            raise DuplicateScanError from None

    def get_by_id(self, scan_id: str) -> ScanRecord:
        scan = self._session.get(Scan, scan_id)
        if scan is None:
            raise ScanNotFound
        return _to_record(scan)

    def list_incomplete(self) -> list[ScanRecord]:
        stmt = select(Scan).where(Scan.status.in_(_INCOMPLETE_SCAN_STATUSES))
        scans = self._session.scalars(stmt).all()
        return [_to_record(scan) for scan in scans]

    def mark_processing(self, scan_id: str) -> ScanRecord:
        scan = self._require_scan(scan_id)
        now = _utc_now()
        scan.status = ScanStatus.PROCESSING
        scan.started_at = now
        scan.updated_at = now
        return _to_record(scan)

    def mark_completed(
        self,
        scan_id: str,
        result: ATSScanResult,
        *,
        job_title: str | None = None,
    ) -> None:
        scan = self._require_scan(scan_id)
        now = _utc_now()
        scan.status = ScanStatus.COMPLETED
        scan.ats_score = result.overall_score
        scan.job_title_detected = job_title
        scan.failure_reason = None
        scan.result_json = result.model_dump_json()
        scan.completed_at = now
        scan.updated_at = now

    def mark_failed(self, scan_id: str, reason: str) -> None:
        scan = self._require_scan(scan_id)
        now = _utc_now()
        scan.status = ScanStatus.FAILED
        scan.failure_reason = reason
        scan.result_json = None
        scan.ats_score = None
        scan.completed_at = now
        scan.updated_at = now

    def mark_webhook_processing_sent(self, scan_id: str) -> None:
        scan = self._require_scan(scan_id)
        scan.webhook_processing_sent = True
        scan.updated_at = _utc_now()

    def mark_webhook_terminal_sent(self, scan_id: str) -> None:
        scan = self._require_scan(scan_id)
        scan.webhook_terminal_sent = True
        scan.updated_at = _utc_now()

    def _require_scan(self, scan_id: str) -> Scan:
        scan = self._session.get(Scan, scan_id)
        if scan is None:
            raise ScanNotFound
        return scan
