from core.logger import configure_logging
from infra.http.app import get_app

configure_logging()

app = get_app()
