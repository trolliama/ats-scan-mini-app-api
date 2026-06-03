from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.exceptions import DuplicateScanError, ScanNotFound
from core.models import ATSScanResult
from infra.db.unit_of_work import UoWContext, commit, unit_of_work
from tests.factories import ATSScanResultFactory, ScanCreateFactory


@pytest.fixture
def uow(db_session_factory) -> UoWContext:
    with unit_of_work(db_session_factory) as ctx:
        yield ctx


def _commit(uow: UoWContext) -> None:
    commit(uow)


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
        uow: UoWContext,
    ) -> None:
        """Inserting a pending scan persists input fields and default lifecycle values."""
        record = ScanCreateFactory.build()
        uow.scans.insert_pending(record)
        _commit(uow)

        row = _fetch_scan(uow.session, str(record.scan_id))

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
        uow: UoWContext,
    ) -> None:
        """Inserting the same scan_id twice raises DuplicateScanError and leaves one row."""
        record = ScanCreateFactory.build()
        uow.scans.insert_pending(record)
        _commit(uow)

        with pytest.raises(DuplicateScanError):
            uow.scans.insert_pending(record)

        assert _count_scans(uow.session, str(record.scan_id)) == 1

    def test_raises_scan_not_found_when_getting_unknown_scan(
        self, uow: UoWContext
    ) -> None:
        """get_by_id raises ScanNotFound when no scan exists for the given id."""
        with pytest.raises(ScanNotFound):
            uow.scans.get_by_id(str(uuid4()))

    def test_returns_only_pending_and_processing_when_listing_incomplete(
        self, uow: UoWContext
    ) -> None:
        """list_incomplete excludes completed and failed scans."""
        pending, processing, completed, failed = ScanCreateFactory.build_batch(4)

        for scan in (pending, processing, completed, failed):
            uow.scans.insert_pending(scan)

        uow.scans.mark_processing(str(processing.scan_id))
        uow.scans.mark_completed(
            str(completed.scan_id),
            ATSScanResultFactory.build(overall_score=80),
            job_title="Engineer",
        )
        uow.scans.mark_failed(str(failed.scan_id), "S3 object not found")
        _commit(uow)

        incomplete_ids = {row.id for row in uow.scans.list_incomplete()}

        assert incomplete_ids == {str(pending.scan_id), str(processing.scan_id)}

    def test_sets_status_and_started_at_when_marking_processing(
        self,
        uow: UoWContext,
    ) -> None:
        """mark_processing moves the scan to processing and records started_at."""
        record = ScanCreateFactory.build()
        uow.scans.insert_pending(record)
        _commit(uow)
        before = _fetch_scan(uow.session, str(record.scan_id))
        assert before is not None

        uow.scans.mark_processing(str(record.scan_id))
        _commit(uow)

        after = _fetch_scan(uow.session, str(record.scan_id))
        assert after is not None
        assert after["status"] == "processing"
        assert after["started_at"] is not None
        assert after["updated_at"] >= before["updated_at"]
        assert after["completed_at"] is None

    def test_persists_result_and_terminal_fields_when_marking_completed(
        self,
        uow: UoWContext,
    ) -> None:
        """mark_completed stores the ATS result, job title, and terminal timestamps."""
        record = ScanCreateFactory.build()
        uow.scans.insert_pending(record)
        uow.scans.mark_processing(str(record.scan_id))
        result = ATSScanResultFactory.build(overall_score=85)

        uow.scans.mark_completed(
            str(record.scan_id),
            result,
            job_title="Software Engineer",
        )
        _commit(uow)

        row = _fetch_scan(uow.session, str(record.scan_id))
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
        uow: UoWContext,
    ) -> None:
        """mark_failed stores the failure reason and clears result fields."""
        record = ScanCreateFactory.build()
        uow.scans.insert_pending(record)
        uow.scans.mark_processing(str(record.scan_id))

        uow.scans.mark_failed(str(record.scan_id), "S3 object not found: key")
        _commit(uow)

        row = _fetch_scan(uow.session, str(record.scan_id))
        assert row is not None
        assert row["status"] == "failed"
        assert row["failure_reason"] == "S3 object not found: key"
        assert row["completed_at"] is not None
        assert row["result_json"] is None
        assert row["ats_score"] is None

    def test_persists_webhook_sent_flags_when_marking_webhooks_sent(
        self,
        uow: UoWContext,
    ) -> None:
        """Webhook idempotency flags flip independently for processing and terminal events."""
        record = ScanCreateFactory.build()
        uow.scans.insert_pending(record)

        uow.scans.mark_webhook_processing_sent(str(record.scan_id))
        _commit(uow)
        after_processing = _fetch_scan(uow.session, str(record.scan_id))
        assert after_processing is not None
        assert after_processing["webhook_processing_sent"] == 1
        assert after_processing["webhook_terminal_sent"] == 0

        uow.scans.mark_webhook_terminal_sent(str(record.scan_id))
        _commit(uow)
        after_terminal = _fetch_scan(uow.session, str(record.scan_id))
        assert after_terminal is not None
        assert after_terminal["webhook_processing_sent"] == 1
        assert after_terminal["webhook_terminal_sent"] == 1
