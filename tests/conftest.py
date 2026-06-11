import os

_TEST_ENV_DEFAULTS = {
    "API_KEY": "test-api-key",
    "NEXT_WEBHOOK_URL": "http://localhost:3000/api/ats/webhook",
    "WEBHOOK_SECRET": "test-webhook-secret",
    "S3_ENDPOINT": "http://localhost:9000",
    "S3_BUCKET": "test-bucket",
    "S3_ACCESS_KEY": "test-access-key",
    "S3_SECRET_KEY": "test-secret-key",
    "S3_REGION": "us-east-1",
}

for _key, _value in _TEST_ENV_DEFAULTS.items():
    os.environ.setdefault(_key, _value)
