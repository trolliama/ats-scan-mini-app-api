import hashlib
import hmac
import logging
import time
from datetime import timedelta

import httpx
import pytest
import respx
from freezegun import freeze_time

from core.config import Settings
from core.enums import ScanStatus
from core.logger import configure_logging
from infra.http.schemas import (
    WebhookCompletedPayload,
    WebhookFailedPayload,
    WebhookProcessingPayload,
)
from infra.webhooks.client import send_completed, send_failed, send_processing
from tests.factories import ATSScanResultFactory

_SCAN_ID = "scan-123"
_ATS_SCORE = 72
_JOB_TITLE = "Software Engineer"
_FAILURE_REASON = "S3 object not found: resumes/missing.pdf"
_ATS_RESULT = ATSScanResultFactory.build(overall_score=_ATS_SCORE)
_TOTAL_RETRY_SLEEP = 13


@pytest.fixture(autouse=True)
def _configure_logging() -> None:
    configure_logging()


@pytest.fixture
def webhook_retry_clock(monkeypatch: pytest.MonkeyPatch):
    """Instant retry backoff with a fake clock (freezegun tick, no real sleep)."""
    with freeze_time("2024-01-01 00:00:00") as frozen:
        def _instant_sleep(seconds: float) -> None:
            frozen.tick(delta=timedelta(seconds=seconds))

        monkeypatch.setattr("infra.webhooks.client.time.sleep", _instant_sleep)
        yield frozen


def _assert_delivered_with_hmac(
    result: bool,
    call: httpx.Request,
    settings: Settings,
    expected_body: bytes,
) -> None:
    expected_signature = (
        "sha256="
        + hmac.new(
            settings.webhook_secret.encode(), expected_body, hashlib.sha256
        ).hexdigest()
    )

    assert result is True
    assert call.url == settings.next_webhook_url
    assert call.content == expected_body
    assert call.headers["X-Webhook-Signature"] == expected_signature


def _assert_retries_exhausted(
    result: bool,
    route: respx.Route,
    caplog: pytest.LogCaptureFixture,
    *,
    elapsed: float,
) -> None:
    assert result is False
    assert route.call_count == 4
    assert elapsed == _TOTAL_RETRY_SLEEP
    assert "webhook_delivery_exhausted" in caplog.text


class TestSendProcessing:
    def test_returns_true_with_hmac_when_post_succeeds(
        self, settings: Settings
    ) -> None:
        """send_processing returns True and posts a valid HMAC-SHA256 signature on 2xx."""
        expected_body = WebhookProcessingPayload(
            scanId=_SCAN_ID, status=ScanStatus.PROCESSING
        ).model_dump_json().encode()

        with respx.mock:
            route = respx.post(settings.next_webhook_url).mock(
                return_value=httpx.Response(200)
            )
            result = send_processing(_SCAN_ID, settings)

        _assert_delivered_with_hmac(
            result, route.calls.last.request, settings, expected_body
        )

    def test_returns_false_when_post_always_returns_500(
        self,
        settings: Settings,
        caplog: pytest.LogCaptureFixture,
        webhook_retry_clock,
    ) -> None:
        """send_processing returns False after 4 attempts when every response is non-2xx."""
        caplog.set_level(logging.ERROR)
        start = time.time()

        with respx.mock:
            route = respx.post(settings.next_webhook_url).mock(
                return_value=httpx.Response(500)
            )
            result = send_processing(_SCAN_ID, settings)

        _assert_retries_exhausted(
            result, route, caplog, elapsed=time.time() - start
        )


class TestSendCompleted:
    def test_returns_true_with_hmac_when_post_succeeds(
        self, settings: Settings
    ) -> None:
        """send_completed returns True and posts a valid HMAC-SHA256 signature on 2xx."""
        expected_body = WebhookCompletedPayload(
            scanId=_SCAN_ID,
            status="completed",
            atsScore=_ATS_SCORE,
            jobTitleDetected=_JOB_TITLE,
            result=_ATS_RESULT,
        ).model_dump_json().encode()

        with respx.mock:
            route = respx.post(settings.next_webhook_url).mock(
                return_value=httpx.Response(200)
            )
            result = send_completed(
                _SCAN_ID, _ATS_SCORE, _JOB_TITLE, _ATS_RESULT, settings
            )

        _assert_delivered_with_hmac(
            result, route.calls.last.request, settings, expected_body
        )

    def test_returns_false_when_post_always_returns_500(
        self,
        settings: Settings,
        caplog: pytest.LogCaptureFixture,
        webhook_retry_clock,
    ) -> None:
        """send_completed returns False after 4 attempts when every response is non-2xx."""
        caplog.set_level(logging.ERROR)
        start = time.time()

        with respx.mock:
            route = respx.post(settings.next_webhook_url).mock(
                return_value=httpx.Response(500)
            )
            result = send_completed(
                _SCAN_ID, _ATS_SCORE, _JOB_TITLE, _ATS_RESULT, settings
            )

        _assert_retries_exhausted(
            result, route, caplog, elapsed=time.time() - start
        )


class TestSendFailed:
    def test_returns_true_with_hmac_when_post_succeeds(
        self, settings: Settings
    ) -> None:
        """send_failed returns True and posts a valid HMAC-SHA256 signature on 2xx."""
        expected_body = WebhookFailedPayload(
            scanId=_SCAN_ID,
            status="failed",
            failureReason=_FAILURE_REASON,
        ).model_dump_json().encode()

        with respx.mock:
            route = respx.post(settings.next_webhook_url).mock(
                return_value=httpx.Response(200)
            )
            result = send_failed(_SCAN_ID, _FAILURE_REASON, settings)

        _assert_delivered_with_hmac(
            result, route.calls.last.request, settings, expected_body
        )

    def test_returns_false_when_post_always_returns_500(
        self,
        settings: Settings,
        caplog: pytest.LogCaptureFixture,
        webhook_retry_clock,
    ) -> None:
        """send_failed returns False after 4 attempts when every response is non-2xx."""
        caplog.set_level(logging.ERROR)
        start = time.time()

        with respx.mock:
            route = respx.post(settings.next_webhook_url).mock(
                return_value=httpx.Response(500)
            )
            result = send_failed(_SCAN_ID, _FAILURE_REASON, settings)

        _assert_retries_exhausted(
            result, route, caplog, elapsed=time.time() - start
        )
