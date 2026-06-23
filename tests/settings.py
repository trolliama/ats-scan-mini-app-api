from pathlib import Path

from core.config import Settings


def make_test_settings(**overrides: object) -> Settings:
    """Build Settings for tests without reading .env or os.environ."""
    defaults: dict[str, object] = {
        "sqlite_path": Path(":memory:"),
        "skip_app_lifespan": True,
        "api_key": "test-api-key",
        "next_webhook_url": "http://localhost:3000/api/ats/webhook",
        "webhook_secret": "test-webhook-secret",
        "s3_endpoint": "http://localhost:9000",
        "s3_bucket": "test-bucket",
        "s3_access_key": "test-access-key",
        "s3_secret_key": "test-secret-key",
        "s3_region": "us-east-1",
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)
