from collections.abc import Generator
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from core.config import Settings
from infra.http.app import get_app
from tests.factories import ScanCreateFactory


@pytest.fixture
def api_client(
    db_session_factory: sessionmaker[Session],
) -> Generator[TestClient, None, None]:
    app = get_app()
    app.state.session_factory = db_session_factory
    with (
        patch("infra.http.routes.process_scan"),
        TestClient(app) as client,
    ):
        yield client


def _scan_payload(**overrides: object) -> dict[str, str]:
    record = ScanCreateFactory.build(**overrides)
    return {
        "scan_id": str(record.scan_id),
        "session_id": str(record.session_id),
        "file_key": record.file_key,
        "original_filename": record.original_filename,
        "bucket": record.bucket,
    }


def _auth_headers(
    settings: Settings, *, api_key: str | None = None
) -> dict[str, str]:
    return {"X-API-Key": api_key if api_key is not None else settings.api_key}


class TestCreateScanRoute:
    def test_returns_202_when_request_is_valid(
        self, api_client: TestClient, settings: Settings
    ) -> None:
        """Valid API key and body return 202 with pending status."""
        payload = _scan_payload()

        response = api_client.post(
            "/scans", json=payload, headers=_auth_headers(settings)
        )

        assert response.status_code == 202
        body = response.json()
        assert body["scan_id"] == payload["scan_id"]
        assert body["status"] == "pending"

    def test_returns_401_when_api_key_is_missing(
        self, api_client: TestClient
    ) -> None:
        """Missing X-API-Key header returns 401."""
        payload = _scan_payload()

        response = api_client.post("/scans", json=payload)

        assert response.status_code == 401

    def test_returns_401_when_api_key_is_invalid(
        self, api_client: TestClient, settings: Settings
    ) -> None:
        """Wrong X-API-Key header returns 401."""
        payload = _scan_payload()

        response = api_client.post(
            "/scans",
            json=payload,
            headers=_auth_headers(settings, api_key="wrong-key"),
        )

        assert response.status_code == 401

    def test_returns_409_when_scan_id_already_exists(
        self, api_client: TestClient, settings: Settings
    ) -> None:
        """Duplicate scan_id returns 409 on the second request."""
        payload = _scan_payload()
        headers = _auth_headers(settings)

        first = api_client.post("/scans", json=payload, headers=headers)
        second = api_client.post("/scans", json=payload, headers=headers)

        assert first.status_code == 202
        assert second.status_code == 409

    def test_returns_422_when_scan_id_is_not_uuid(
        self, api_client: TestClient, settings: Settings
    ) -> None:
        """Non-UUID scan_id returns 422 validation error."""
        payload = _scan_payload()
        payload["scan_id"] = "not-a-uuid"

        response = api_client.post(
            "/scans", json=payload, headers=_auth_headers(settings)
        )

        assert response.status_code == 422

    def test_returns_404_for_legacy_analyze_routes(
        self, api_client: TestClient
    ) -> None:
        """Legacy /resume/analyze routes no longer exist."""
        job_id = str(uuid4())

        post_response = api_client.post("/resume/analyze")
        get_response = api_client.get(f"/resume/analyze/{job_id}")

        assert post_response.status_code == 404
        assert get_response.status_code == 404
