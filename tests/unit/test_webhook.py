import hashlib
import hmac
from contextlib import contextmanager
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest

from core.config import Settings
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


@pytest.fixture
def settings() -> Settings:
    return Settings(
        api_key="test-api-key",
        next_webhook_url="http://localhost:3000/api/ats/webhook",
        webhook_secret="test-webhook-secret",
        s3_endpoint="http://localhost:9000",
        s3_bucket="test-bucket",
        s3_access_key="test-access-key",
        s3_secret_key="test-secret-key",
        s3_region="us-east-1",
    )


@contextmanager
def _successful_http_client() -> Iterator[MagicMock]:
    mock_response = MagicMock()
    mock_response.is_success = True
    mock_client = MagicMock()
    mock_client.post.return_value = mock_response
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with patch("infra.webhooks.client.httpx.Client", return_value=mock_client):
        yield mock_client


@contextmanager
def _failing_http_client() -> Iterator[tuple[MagicMock, MagicMock, MagicMock]]:
    mock_response = MagicMock()
    mock_response.is_success = False
    mock_client = MagicMock()
    mock_client.post.return_value = mock_response
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with (
        patch("infra.webhooks.client.httpx.Client", return_value=mock_client),
        patch("infra.webhooks.client.time.sleep") as mock_sleep,
        patch("infra.webhooks.client._logger.error") as mock_log_error,
    ):
        yield mock_client, mock_sleep, mock_log_error


def _assert_delivered_with_hmac(
    result: bool,
    mock_client: MagicMock,
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
    mock_client.post.assert_called_once()
    call_kwargs = mock_client.post.call_args
    assert call_kwargs.args[0] == settings.next_webhook_url
    assert call_kwargs.kwargs["content"] == expected_body
    assert (
        call_kwargs.kwargs["headers"]["X-Webhook-Signature"]
        == expected_signature
    )


def _assert_retries_exhausted(
    result: bool,
    mock_client: MagicMock,
    mock_sleep: MagicMock,
    mock_log_error: MagicMock,
) -> None:
    assert result is False
    assert mock_client.post.call_count == 4
    assert mock_sleep.call_args_list == [((1,),), ((3,),), ((9,),)]
    mock_log_error.assert_called_once()


class TestSendProcessing:
    def test_returns_true_with_hmac_when_post_succeeds(
        self, settings: Settings
    ) -> None:
        """send_processing returns True and posts a valid HMAC-SHA256 signature on 2xx."""
        expected_body = WebhookProcessingPayload(
            scanId=_SCAN_ID, status="processing"
        ).model_dump_json().encode()

        with _successful_http_client() as mock_client:
            result = send_processing(_SCAN_ID, settings)

        _assert_delivered_with_hmac(
            result, mock_client, settings, expected_body
        )

    def test_returns_false_when_post_always_returns_500(
        self, settings: Settings
    ) -> None:
        """send_processing returns False after 4 attempts when every response is non-2xx."""
        with _failing_http_client() as (
            mock_client,
            mock_sleep,
            mock_log_error,
        ):
            result = send_processing(_SCAN_ID, settings)

        _assert_retries_exhausted(
            result, mock_client, mock_sleep, mock_log_error
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

        with _successful_http_client() as mock_client:
            result = send_completed(
                _SCAN_ID, _ATS_SCORE, _JOB_TITLE, _ATS_RESULT, settings
            )

        _assert_delivered_with_hmac(
            result, mock_client, settings, expected_body
        )

    def test_returns_false_when_post_always_returns_500(
        self, settings: Settings
    ) -> None:
        """send_completed returns False after 4 attempts when every response is non-2xx."""
        with _failing_http_client() as (
            mock_client,
            mock_sleep,
            mock_log_error,
        ):
            result = send_completed(
                _SCAN_ID, _ATS_SCORE, _JOB_TITLE, _ATS_RESULT, settings
            )

        _assert_retries_exhausted(
            result, mock_client, mock_sleep, mock_log_error
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

        with _successful_http_client() as mock_client:
            result = send_failed(_SCAN_ID, _FAILURE_REASON, settings)

        _assert_delivered_with_hmac(
            result, mock_client, settings, expected_body
        )

    def test_returns_false_when_post_always_returns_500(
        self, settings: Settings
    ) -> None:
        """send_failed returns False after 4 attempts when every response is non-2xx."""
        with _failing_http_client() as (
            mock_client,
            mock_sleep,
            mock_log_error,
        ):
            result = send_failed(_SCAN_ID, _FAILURE_REASON, settings)

        _assert_retries_exhausted(
            result, mock_client, mock_sleep, mock_log_error
        )
