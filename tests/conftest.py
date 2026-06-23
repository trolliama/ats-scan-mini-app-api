from collections.abc import Generator
from pathlib import Path

import boto3
import httpx
import pytest
import respx
from moto import mock_aws

from core import config
from core.config import Settings
from tests.settings import make_test_settings

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session", autouse=True)
def settings() -> Generator[Settings, None, None]:
    """Replace config.get_settings() for the entire test session."""
    test_settings = make_test_settings()
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(config, "get_settings", lambda: test_settings)
    monkeypatch.setenv("MOTO_S3_CUSTOM_ENDPOINTS", test_settings.s3_endpoint)
    config.reset_settings_cache()
    yield test_settings
    monkeypatch.undo()
    config.reset_settings_cache()


@pytest.fixture
def mock_aws_s3() -> Generator[None, None, None]:
    with mock_aws():
        yield


@pytest.fixture
def s3_client(mock_aws_s3: None, settings: Settings) -> Generator:
    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
    )
    yield client


@pytest.fixture
def sample_resume_bytes() -> bytes:
    return (FIXTURES_DIR / "sample_resume.pdf").read_bytes()


@pytest.fixture
def blank_resume_bytes() -> bytes:
    return (FIXTURES_DIR / "blank_resume.pdf").read_bytes()


@pytest.fixture
def webhook_respx(settings: Settings) -> Generator[respx.Router, None, None]:
    with respx.mock(assert_all_called=False) as router:
        router.post(settings.next_webhook_url).mock(
            return_value=httpx.Response(200)
        )
        yield router
