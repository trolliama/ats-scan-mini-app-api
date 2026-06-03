def send_processing_webhook(scan_id: str) -> None:
    """Deferred: ATS scan worker — notify Next.js that processing started."""
    raise NotImplementedError


def send_completed_webhook(scan_id: str, ats_score: int, job_title: str | None, result) -> None:
    """Deferred: ATS scan worker — deliver completed ATS result to Next.js."""
    raise NotImplementedError


def send_failed_webhook(scan_id: str, failure_reason: str) -> None:
    """Deferred: ATS scan worker — notify Next.js that the scan failed."""
    raise NotImplementedError
