from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from db.scan_repository import DuplicateScanError, ScanNotFound, ScanRepository
from scan.schemas import ATSScanResult
from tests.factories import ATSScanResultFactory, ScanCreateFactory


@pytest.fixture
def scan_repository(db_session: Session) -> ScanRepository:
    return ScanRepository(db_session)


def _fetch_scan(session: Session, scan_id: str) -> dict[str, object] | None:
    row = session.execute(
        text("SELECT * FROM scans WHERE id = :id"),
        {"id": scan_id},
    ).mappings().first()
    return dict(row) if row else None


def _count_scans(session: Session, scan_id: str) -> int:
    return session.execute(
        text("SELECT COUNT(*) FROM scans WHERE id = :id"),
        {"id": scan_id},
    ).scalar_one()


class TestScanRepository:
    def test_persists_retrievable_scan_when_insert_pending(
        self,
        db_session: Session,
        scan_repository: ScanRepository,
    ) -> None:
        """Inserting a pending scan persists input fields and default lifecycle values."""
        record = ScanCreateFactory.build()
        scan_repository.insert_pending(record)

        row = _fetch_scan(db_session, str(record.scan_id))

        assert row is not None
        assert row["id"] == str(record.scan_id)
        assert row["session_id"] == str(record.session_id)
        assert row["file_key"] == record.file_key
        assert row["bucket"] == record.bucket
        assert row["original_filename"] == record.original_filename
        assert row["status"] == "pending"
        assert row["webhook_processing_sent"] == 0
        assert row["webhook_terminal_sent"] == 0
        assert row["created_at"] is not None
        assert row["updated_at"] is not None
        assert row["started_at"] is None
        assert row["completed_at"] is None

    def test_raises_duplicate_scan_error_when_scan_already_exists(
        self,
        db_session: Session,
        scan_repository: ScanRepository,
    ) -> None:
        """Inserting the same scan_id twice raises DuplicateScanError and leaves one row."""
        record = ScanCreateFactory.build()
        scan_repository.insert_pending(record)

        with pytest.raises(DuplicateScanError):
            scan_repository.insert_pending(record)

        assert _count_scans(db_session, str(record.scan_id)) == 1

    def test_raises_scan_not_found_when_getting_unknown_scan(
        self, scan_repository: ScanRepository
    ) -> None:
        """get_by_id raises ScanNotFound when no scan exists for the given id."""
        with pytest.raises(ScanNotFound):
            scan_repository.get_by_id(str(uuid4()))

    def test_returns_only_pending_and_processing_when_listing_incomplete(
        self, scan_repository: ScanRepository
    ) -> None:
        """list_incomplete excludes completed and failed scans."""
        pending, processing, completed, failed = ScanCreateFactory.build_batch(4)

        for scan in (pending, processing, completed, failed):
            scan_repository.insert_pending(scan)

        scan_repository.mark_processing(str(processing.scan_id))
        scan_repository.mark_completed(
            str(completed.scan_id),
            ATSScanResultFactory.build(overall_score=80),
            job_title="Engineer",
        )
        scan_repository.mark_failed(str(failed.scan_id), "S3 object not found")

        incomplete_ids = {row.id for row in scan_repository.list_incomplete()}

        assert incomplete_ids == {str(pending.scan_id), str(processing.scan_id)}

    def test_sets_status_and_started_at_when_marking_processing(
        self,
        db_session: Session,
        scan_repository: ScanRepository,
    ) -> None:
        """mark_processing moves the scan to processing and records started_at."""
        record = ScanCreateFactory.build()
        scan_repository.insert_pending(record)
        before = _fetch_scan(db_session, str(record.scan_id))
        assert before is not None

        scan_repository.mark_processing(str(record.scan_id))

        after = _fetch_scan(db_session, str(record.scan_id))
        assert after is not None
        assert after["status"] == "processing"
        assert after["started_at"] is not None
        assert after["updated_at"] >= before["updated_at"]
        assert after["completed_at"] is None

    def test_persists_result_and_terminal_fields_when_marking_completed(
        self,
        db_session: Session,
        scan_repository: ScanRepository,
    ) -> None:
        """mark_completed stores the ATS result, job title, and terminal timestamps."""
        record = ScanCreateFactory.build()
        scan_repository.insert_pending(record)
        scan_repository.mark_processing(str(record.scan_id))
        result = ATSScanResultFactory.build(overall_score=85)

        scan_repository.mark_completed(
            str(record.scan_id),
            result,
            job_title="Software Engineer",
        )

        row = _fetch_scan(db_session, str(record.scan_id))
        assert row is not None
        assert row["status"] == "completed"
        assert row["ats_score"] == 85
        assert row["job_title_detected"] == "Software Engineer"
        assert row["completed_at"] is not None
        assert row["failure_reason"] is None
        assert row["result_json"] is not None
        assert ATSScanResult.model_validate_json(row["result_json"]) == result

    def test_persists_reason_and_terminal_fields_when_marking_failed(
        self,
        db_session: Session,
        scan_repository: ScanRepository,
    ) -> None:
        """mark_failed stores the failure reason and clears result fields."""
        record = ScanCreateFactory.build()
        scan_repository.insert_pending(record)
        scan_repository.mark_processing(str(record.scan_id))

        scan_repository.mark_failed(str(record.scan_id), "S3 object not found: key")

        row = _fetch_scan(db_session, str(record.scan_id))
        assert row is not None
        assert row["status"] == "failed"
        assert row["failure_reason"] == "S3 object not found: key"
        assert row["completed_at"] is not None
        assert row["result_json"] is None
        assert row["ats_score"] is None

    def test_persists_webhook_sent_flags_when_marking_webhooks_sent(
        self,
        db_session: Session,
        scan_repository: ScanRepository,
    ) -> None:
        """Webhook idempotency flags flip independently for processing and terminal events."""
        record = ScanCreateFactory.build()
        scan_repository.insert_pending(record)

        scan_repository.mark_webhook_processing_sent(str(record.scan_id))
        after_processing = _fetch_scan(db_session, str(record.scan_id))
        assert after_processing is not None
        assert after_processing["webhook_processing_sent"] == 1
        assert after_processing["webhook_terminal_sent"] == 0

        scan_repository.mark_webhook_terminal_sent(str(record.scan_id))
        after_terminal = _fetch_scan(db_session, str(record.scan_id))
        assert after_terminal is not None
        assert after_terminal["webhook_processing_sent"] == 1
        assert after_terminal["webhook_terminal_sent"] == 1
