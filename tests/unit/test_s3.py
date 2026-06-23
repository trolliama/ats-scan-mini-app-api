import pytest
from botocore.exceptions import ClientError

from core.exceptions import S3ObjectNotFoundError
from infra.storage.s3 import fetch_object


def test_returns_object_bytes_when_s3_get_object_succeeds(s3_client) -> None:
    """fetch_object returns the bytes read from the S3 object body on success."""
    expected = b"%PDF-1.4 resume content"
    s3_client.create_bucket(Bucket="my-bucket")
    s3_client.put_object(Bucket="my-bucket", Key="resumes/file.pdf", Body=expected)

    result = fetch_object("my-bucket", "resumes/file.pdf")

    assert result == expected


def test_raises_s3_object_not_found_error_when_s3_returns_404(s3_client) -> None:
    """fetch_object raises S3ObjectNotFoundError with the file key when S3 returns 404."""
    file_key = "resumes/missing.pdf"
    s3_client.create_bucket(Bucket="my-bucket")

    with pytest.raises(
        S3ObjectNotFoundError, match=f"S3 object not found: {file_key}"
    ):
        fetch_object("my-bucket", file_key)
