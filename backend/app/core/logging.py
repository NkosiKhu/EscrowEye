from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from pythonjsonlogger import jsonlogger


_LOG_DIR: Path | None = None
_LOGGERS: dict[str, logging.Logger] = {}


class ContextFilter(logging.Filter):
    def __init__(self, extra: dict[str, str] | None = None):
        super().__init__()
        self._static = extra or {}

    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in self._static.items():
            if not hasattr(record, key):
                setattr(record, key, value)
        if not hasattr(record, "timestamp"):
            record.timestamp = datetime.now(timezone.utc).isoformat()
        return True


class RequestContextFilter(ContextFilter):
    def __init__(self) -> None:
        super().__init__()
        self._request_id: str = ""
        self._user_id: str = ""
        self._path: str = ""

    def set_context(self, request_id: str, user_id: str = "", path: str = "") -> None:
        self._request_id = request_id
        self._user_id = user_id
        self._path = path

    def filter(self, record: logging.LogRecord) -> bool:
        record.timestamp = datetime.now(timezone.utc).isoformat()
        record.request_id = self._request_id or "-"
        record.user_id = self._user_id or "-"
        record.path = self._path or "-"
        return True


_request_context = RequestContextFilter()


def configure_logging() -> None:
    global _LOG_DIR

    level_name = os.getenv("ESCROWEYE_LOG_LEVEL", "DEBUG").upper()
    level = getattr(logging, level_name, logging.DEBUG)

    log_dir = os.getenv("ESCROWEYE_LOG_DIR", "")
    if log_dir:
        _LOG_DIR = Path(log_dir)
        _LOG_DIR.mkdir(parents=True, exist_ok=True)

    json_format = os.getenv("ESCROWEYE_LOG_FORMAT", "text")
    use_json = json_format.lower() in ("json", "structured")

    root = logging.getLogger()
    root.setLevel(level)

    for handler in root.handlers[:]:
        root.removeHandler(handler)

    fmt_string = "%(timestamp)s %(levelname)s [%(name)s] [%(request_id)s] [%(user_id)s] %(message)s"
    if use_json:
        formatter = jsonlogger.JsonFormatter(
            fmt="%(timestamp)s %(levelname)s %(name)s %(request_id)s %(user_id)s %(path)s %(message)s",
            rename_fields={"levelname": "severity", "name": "logger", "message": "message"},
        )
    else:
        formatter = logging.Formatter(fmt_string)

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(formatter)
    console.addFilter(_request_context)
    root.addHandler(console)

    if _LOG_DIR:
        file_path = _LOG_DIR / "escroweye.log"
        file_handler = RotatingFileHandler(
            str(file_path),
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(_request_context)
        root.addHandler(file_handler)

        err_path = _LOG_DIR / "escroweye-error.log"
        err_handler = RotatingFileHandler(
            str(err_path),
            maxBytes=10 * 1024 * 1024,
            backupCount=3,
        )
        err_handler.setLevel(logging.ERROR)
        err_handler.setFormatter(formatter)
        err_handler.addFilter(_request_context)
        root.addHandler(err_handler)

    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)
    logging.getLogger("hierosdk").setLevel(logging.WARNING)

    get_logger("escroweye.initialized").info(
        "Logging configured",
        extra={"log_level": level_name, "log_format": json_format, "log_dir": str(_LOG_DIR or "console-only")},
    )


def get_logger(name: str) -> logging.Logger:
    if name in _LOGGERS:
        return _LOGGERS[name]
    logger = logging.getLogger(name)
    _LOGGERS[name] = logger
    return logger


def get_request_context() -> RequestContextFilter:
    return _request_context


def set_request_context(request_id: str, user_id: str = "", path: str = "") -> None:
    _request_context.set_context(request_id, user_id, path)


class LoggerMixin:
    @property
    def log(self) -> logging.Logger:
        cls = type(self)
        name = f"{cls.__module__}.{cls.__qualname__}"
        return get_logger(name)
