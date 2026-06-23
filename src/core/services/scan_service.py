from sqlalchemy.orm import Session, sessionmaker

from ai.agent import run_agent
from ai.resume_parser import extract_cv_preview, extract_markdown_from_resume
from core import config
from core.enums import ScanStatus
from core.exceptions import ScanNotFound
from core.logger import get_logger
from core.models import ATSScanResult, ScanCreate
from infra.db.unit_of_work import UoWContext, commit, unit_of_work
from infra.http.schemas import CreateScanRequest, CreateScanResponse
from infra.storage.s3 import fetch_object
from infra.webhooks.client import send_completed, send_failed, send_processing

_TERMINAL_SCAN_STATUSES = frozenset({ScanStatus.COMPLETED, ScanStatus.FAILED})


def create_scan(
    uow: UoWContext, body: CreateScanRequest
) -> CreateScanResponse:
    """Insert a pending scan record for background processing."""
    record = ScanCreate(
        scan_id=body.scan_id,
        session_id=body.session_id,
        file_key=body.file_key,
        bucket=body.bucket,
        original_filename=body.original_filename,
    )

    uow.scans.insert_pending(record)
    commit(uow)

    return CreateScanResponse(scan_id=body.scan_id, status=ScanStatus.PENDING)


def recover_incomplete_scans(
    session_factory: sessionmaker[Session],
) -> list[str]:
    """Return scan ids in pending or processing state for startup recovery."""
    with unit_of_work(session_factory) as uow:
        scan_ids = [record.id for record in uow.scans.list_incomplete()]
    return scan_ids


def process_scan(scan_id: str, session_factory: sessionmaker[Session]) -> None:
    """Run the ATS scan pipeline for a single scan id."""
    log = get_logger("scan").bind(scan_id=scan_id)

    with unit_of_work(session_factory) as uow:
        try:
            record = uow.scans.get_by_id(scan_id)
        except ScanNotFound:
            log.warning("scan_not_found")
            return

        if record.status in _TERMINAL_SCAN_STATUSES:
            log.info("scan_already_terminal", status=record.status)
            return

        processing_webhook_sent = record.webhook_processing_sent
        uow.scans.mark_processing(scan_id)
        commit(uow)

    if not processing_webhook_sent:
        send_processing(scan_id, config.get_settings())
        with unit_of_work(session_factory) as uow:
            uow.scans.mark_webhook_processing_sent(scan_id)
            commit(uow)

    try:
        with unit_of_work(session_factory) as uow:
            record = uow.scans.get_by_id(scan_id)

        content = fetch_object(record.bucket, record.file_key)
        markdown = extract_markdown_from_resume(
            content, record.original_filename
        )
        log.debug("markdown_extracted", length=len(markdown))
        preview = extract_cv_preview(markdown)
        agent_out = run_agent(markdown)
        result = ATSScanResult(
            overall_score=agent_out.overall_score,
            category_scores=agent_out.category_scores,
            missing_keywords=agent_out.missing_keywords,
            found_keywords=agent_out.found_keywords,
            issues=agent_out.issues,
            cv_preview=preview,
        )

        with unit_of_work(session_factory) as uow:
            uow.scans.mark_completed(
                scan_id,
                result,
                job_title=agent_out.job_title_detected,
            )
            commit(uow)

        send_completed(
            scan_id,
            result.overall_score,
            agent_out.job_title_detected,
            result,
            config.get_settings(),
        )
        with unit_of_work(session_factory) as uow:
            uow.scans.mark_webhook_terminal_sent(scan_id)
            commit(uow)
    except Exception as exc:
        log.exception("scan_failed")
        reason = str(exc)
        with unit_of_work(session_factory) as uow:
            uow.scans.mark_failed(scan_id, reason)
            commit(uow)
        send_failed(scan_id, reason, config.get_settings())
        with unit_of_work(session_factory) as uow:
            uow.scans.mark_webhook_terminal_sent(scan_id)
            commit(uow)
