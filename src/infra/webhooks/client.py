import hashlib
import hmac
import time

import httpx
import structlog
from pydantic import BaseModel

from core.config import Settings
from core.models import ATSScanResult
from infra.http.schemas import (
    WebhookCompletedPayload,
    WebhookFailedPayload,
    WebhookProcessingPayload,
)

_RETRY_DELAYS = (1, 3, 9)
_logger = structlog.get_logger()


def _sign_payload(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _send_webhook(payload: BaseModel, settings: Settings) -> bool:
    body = payload.model_dump_json().encode()
    signature = _sign_payload(body, settings.webhook_secret)
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": signature,
    }

    for attempt in range(len(_RETRY_DELAYS) + 1):
        try:
            with httpx.Client() as client:
                response = client.post(
                    settings.next_webhook_url, content=body, headers=headers
                )
            if response.is_success:
                return True
        except httpx.HTTPError:
            pass

        if attempt < len(_RETRY_DELAYS):
            time.sleep(_RETRY_DELAYS[attempt])

    _logger.error(
        "webhook_delivery_exhausted",
        url=settings.next_webhook_url,
        payload_type=type(payload).__name__,
    )
    return False


def send_processing(scan_id: str, settings: Settings) -> bool:
    payload = WebhookProcessingPayload(scanId=scan_id, status="processing")
    return _send_webhook(payload, settings)


def send_completed(
    scan_id: str,
    ats_score: int,
    job_title_detected: str | None,
    result: ATSScanResult,
    settings: Settings,
) -> bool:
    payload = WebhookCompletedPayload(
        scanId=scan_id,
        status="completed",
        atsScore=ats_score,
        jobTitleDetected=job_title_detected,
        result=result,
    )
    return _send_webhook(payload, settings)


def send_failed(scan_id: str, failure_reason: str, settings: Settings) -> bool:
    payload = WebhookFailedPayload(
        scanId=scan_id,
        status="failed",
        failureReason=failure_reason,
    )
    return _send_webhook(payload, settings)
