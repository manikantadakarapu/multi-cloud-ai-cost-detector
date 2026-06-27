import json
import logging
import sys
from datetime import UTC, datetime
from logging.config import dictConfig
from typing import Any

from app.core.config import settings


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        for key, value in record.__dict__.items():
            if key not in _STANDARD_LOG_RECORD_KEYS and not key.startswith("_"):
                payload[key] = value

        return json.dumps(payload, default=str, separators=(",", ":"))


_STANDARD_LOG_RECORD_KEYS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
    "taskName",
}


def configure_logging() -> None:
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "json": {
                    "()": JsonFormatter,
                }
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "stream": sys.stdout,
                    "formatter": "json",
                }
            },
            "root": {
                "level": settings.log_level,
                "handlers": ["default"],
            },
            "loggers": {
                "uvicorn.access": {
                    "level": settings.log_level,
                    "handlers": ["default"],
                    "propagate": False,
                }
            },
        }
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
