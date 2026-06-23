import logging
import os
import sys

import structlog

from core import config

APP_LOGGER = "mini_app_api"
_configured = False


def format_bytes(size: int) -> str:
    if size < 1024:
        return f"{size}B"
    if size < 1024 * 1024:
        return f"{size // 1024}KB"
    return f"{size / (1024 * 1024):.1f}MB"


class DevRenderer:
    """TIME LEVEL [domain] message  key=value — no structlog [info] padding."""

    _SKIP = frozenset({"timestamp", "level", "domain", "event", "exc_info"})
    _LEVEL_COLOR = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[1m\033[31m",
    }

    def __init__(self, colors: bool) -> None:
        self._colors = colors

    def _c(self, text: str, code: str) -> str:
        return f"{code}{text}\033[0m" if self._colors else text

    def __call__(
        self,
        _logger: object,
        method_name: str,
        event_dict: structlog.types.EventDict,
    ) -> str:
        data = dict(event_dict)
        ts = data.pop("timestamp", "")
        level = str(data.pop("level", method_name)).upper().ljust(5)
        domain = f"[{data.pop('domain', 'app')}]"
        event = data.pop("event", "")
        exception = data.pop("exception", None)

        ts = self._c(ts, "\033[92m")
        level = self._c(level, self._LEVEL_COLOR.get(level.strip(), ""))
        domain = self._c(domain, "\033[36m") if self._colors else domain

        meta = "  ".join(
            (
                f"{self._c(k, '\033[33m')}={self._c(str(v), '\033[35m')}"
                if self._colors
                else f"{k}={v}"
            )
            for k, v in sorted(data.items())
            if k not in self._SKIP and v is not None
        )
        line = f"{ts} {level} {domain} {event}"
        if meta:
            line += f"  {meta}"
        if exception:
            line += f"\n{exception}"
        return line


def _shared_processors(dev: bool) -> list[structlog.types.Processor]:
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(
            fmt="%H:%M:%S" if dev else "iso", utc=not dev
        ),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]


def _renderer(dev: bool) -> structlog.types.Processor:
    if not dev:
        return structlog.processors.JSONRenderer()

    color = config.get_settings().log_color_enabled and not os.environ.get("NO_COLOR")
    return DevRenderer(color)


def _configure_structlog(shared: list[structlog.types.Processor]) -> None:
    structlog.configure(
        processors=shared
        + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        wrapper_class=structlog.make_filtering_bound_logger(
            config.get_settings().log_level_value
        ),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def _build_handler(
    shared: list[structlog.types.Processor],
    renderer: structlog.types.Processor,
) -> logging.Handler:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                renderer,
            ],
        )
    )
    return handler


def _configure_stdlib_logging(handler: logging.Handler) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(config.get_settings().log_level_value)
    root.addHandler(handler)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True
        lg.setLevel(config.get_settings().log_level_value)


def configure_logging() -> None:
    global _configured

    if _configured:
        return
    _configured = True

    dev = config.get_settings().log_env == "dev"
    shared = _shared_processors(dev)
    renderer = _renderer(dev)

    _configure_structlog(shared)
    _configure_stdlib_logging(_build_handler(shared, renderer))


def get_logger(domain: str) -> structlog.stdlib.BoundLogger:
    configure_logging()
    return structlog.get_logger(APP_LOGGER).bind(domain=domain)
