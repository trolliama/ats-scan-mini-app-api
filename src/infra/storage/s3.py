import boto3
from botocore.exceptions import ClientError

from core.config import get_settings
from core.exceptions import S3ObjectNotFoundError


def fetch_object(bucket: str, file_key: str) -> bytes:
    settings = get_settings()
    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
    )
    try:
        response = client.get_object(Bucket=bucket, Key=file_key)
        return response["Body"].read()
    except ClientError as exc:
        response = exc.response
        status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        code = response.get("Error", {}).get("Code")
        if status == 404 or code in ("404", "NoSuchKey"):
            message = f"S3 object not found: {file_key}"
            raise S3ObjectNotFoundError(message) from exc
        raise
