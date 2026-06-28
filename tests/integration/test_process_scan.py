import json

import pytest
import respx
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from core.config import Settings
from core.enums import ATSCategoryKey
from core.models import ATSScanResult
from core.services.scan_service import process_scan
from infra.db.unit_of_work import UoWContext, commit, unit_of_work
from tests.factories import ScanCreateFactory


@pytest.fixture
def uow(db_session_factory: sessionmaker[Session]) -> UoWContext:
    with unit_of_work(db_session_factory) as ctx:
        yield ctx


def _fetch_scan(session: Session, scan_id: str) -> dict[str, object] | None:
    row = session.execute(
        text("SELECT * FROM scans WHERE id = :id"),
        {"id": scan_id},
    ).mappings().first()
    return dict(row) if row else None


def _insert_pending(uow: UoWContext, **overrides: object) -> str:
    record = ScanCreateFactory.build(**overrides)
    uow.scans.insert_pending(record)
    commit(uow)
    return str(record.scan_id)


def _seed_s3_object(
    s3_client,
    body: bytes,
    settings: Settings,
    *,
    bucket: str | None = None,
    file_key: str = "resumes/sess/file.pdf",
) -> None:
    bucket = bucket or settings.s3_bucket
    s3_client.create_bucket(Bucket=bucket)
    s3_client.put_object(Bucket=bucket, Key=file_key, Body=body)


def _webhook_statuses(router: respx.Router) -> list[str]:
    return [
        json.loads(call.request.content)["status"]
        for call in router.calls
    ]


class TestProcessScan:
    def test_marks_completed_when_pipeline_succeeds(
        self,
        db_session_factory: sessionmaker[Session],
        uow: UoWContext,
        s3_client,
        sample_resume_bytes: bytes,
        settings: Settings,
        webhook_respx: respx.Router,
    ) -> None:
        """Happy path persists completed status and sends processing and completed webhooks."""
        scan_id = _insert_pending(uow)
        _seed_s3_object(s3_client, sample_resume_bytes, settings)

        process_scan(scan_id, db_session_factory)

        row = _fetch_scan(uow.session, scan_id)
        assert row is not None
        assert row["status"] == "completed"
        assert row["webhook_processing_sent"] == 1
        assert row["webhook_terminal_sent"] == 1
        assert row["result_json"] is not None
        result = ATSScanResult.model_validate_json(row["result_json"])
        assert result.overall_score == 0
        assert set(result.category_scores.keys()) == set(ATSCategoryKey.all_keys())
        assert result.cv_preview.name == ""
        assert result.cv_preview.contact == []
        assert len(webhook_respx.calls) == 2
        assert _webhook_statuses(webhook_respx) == ["processing", "completed"]

    def test_marks_failed_when_s3_object_missing(
        self,
        db_session_factory: sessionmaker[Session],
        uow: UoWContext,
        s3_client,
        settings: Settings,
        webhook_respx: respx.Router,
    ) -> None:
        """S3 404 marks the scan failed and sends a terminal failed webhook."""
        file_key = "resumes/missing.pdf"
        reason = f"S3 object not found: {file_key}"
        scan_id = _insert_pending(uow, file_key=file_key)
        s3_client.create_bucket(Bucket=settings.s3_bucket)

        process_scan(scan_id, db_session_factory)

        row = _fetch_scan(uow.session, scan_id)
        assert row is not None
        assert row["status"] == "failed"
        assert row["failure_reason"] == reason
        assert row["webhook_terminal_sent"] == 1
        assert len(webhook_respx.calls) == 2
        assert _webhook_statuses(webhook_respx) == ["processing", "failed"]

    def test_marks_failed_when_resume_parse_raises(
        self,
        db_session_factory: sessionmaker[Session],
        uow: UoWContext,
        s3_client,
        blank_resume_bytes: bytes,
        settings: Settings,
        webhook_respx: respx.Router,
    ) -> None:
        """Parse errors mark the scan failed with the exception message as failure_reason."""
        parse_error = "Could not extract text from resume"
        scan_id = _insert_pending(uow)
        _seed_s3_object(s3_client, blank_resume_bytes, settings)

        process_scan(scan_id, db_session_factory)

        row = _fetch_scan(uow.session, scan_id)
        assert row is not None
        assert row["status"] == "failed"
        assert row["failure_reason"] == parse_error
        assert len(webhook_respx.calls) == 2
        assert _webhook_statuses(webhook_respx) == ["processing", "failed"]

    def test_skips_processing_webhook_when_already_sent(
        self,
        db_session_factory: sessionmaker[Session],
        uow: UoWContext,
        s3_client,
        sample_resume_bytes: bytes,
        settings: Settings,
        webhook_respx: respx.Router,
    ) -> None:
        """Recovery resumes without re-sending the processing webhook when the flag is set."""
        scan_id = _insert_pending(uow)
        uow.scans.mark_processing(scan_id)
        uow.scans.mark_webhook_processing_sent(scan_id)
        commit(uow)
        _seed_s3_object(s3_client, sample_resume_bytes, settings)

        process_scan(scan_id, db_session_factory)

        assert len(webhook_respx.calls) == 1
        assert _webhook_statuses(webhook_respx) == ["completed"]
        row = _fetch_scan(uow.session, scan_id)
        assert row is not None
        assert row["status"] == "completed"
