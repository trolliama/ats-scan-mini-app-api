from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from core.exceptions import S3ObjectNotFoundError
from infra.storage.s3 import fetch_object


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.s3_endpoint = "http://localhost:9000"
    settings.s3_access_key = "access-key"
    settings.s3_secret_key = "secret-key"
    settings.s3_region = "us-east-1"

    return settings


def test_returns_object_bytes_when_s3_get_object_succeeds(mock_settings):
    """fetch_object returns the bytes read from the S3 object body on success."""
    expected = b"%PDF-1.4 resume content"
    mock_body = MagicMock()
    mock_body.read.return_value = expected
    mock_client = MagicMock()
    mock_client.get_object.return_value = {"Body": mock_body}

    with (
        patch("infra.storage.s3.get_settings", return_value=mock_settings),
        patch(
            "infra.storage.s3.boto3.client", return_value=mock_client
        ) as mock_boto_client,
    ):
        result = fetch_object("my-bucket", "resumes/file.pdf")

    assert result == expected
    mock_boto_client.assert_called_once_with(
        "s3",
        endpoint_url="http://localhost:9000",
        aws_access_key_id="access-key",
        aws_secret_access_key="secret-key",
        region_name="us-east-1",
    )
    mock_client.get_object.assert_called_once_with(
        Bucket="my-bucket", Key="resumes/file.pdf"
    )


def test_raises_s3_object_not_found_error_when_s3_returns_404(mock_settings):
    """fetch_object raises S3ObjectNotFoundError with the file key when S3 returns 404."""
    file_key = "resumes/missing.pdf"
    error = ClientError(
        {
            "Error": {"Code": "404", "Message": "Not Found"},
            "ResponseMetadata": {"HTTPStatusCode": 404},
        },
        "GetObject",
    )
    mock_client = MagicMock()
    mock_client.get_object.side_effect = error

    with (
        patch("infra.storage.s3.get_settings", return_value=mock_settings),
        patch("infra.storage.s3.boto3.client", return_value=mock_client),
    ):
        with pytest.raises(
            S3ObjectNotFoundError, match=f"S3 object not found: {file_key}"
        ):
            fetch_object("my-bucket", file_key)
