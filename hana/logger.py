"""
hana.logger — Structured JSON logging.

All logs are structured JSON. No print-based logging.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from hana.config import LogLevel


class JSONFormatter(logging.Formatter):
    """Format log records as JSON."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "message": record.getMessage(),
            "logger": record.name,
        }

        if hasattr(record, "sku"):
            log_entry["sku"] = record.sku

        if hasattr(record, "stage"):
            log_entry["stage"] = record.stage

        if hasattr(record, "extra_data"):
            log_entry["data"] = record.extra_data

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False)


class HanaLogger:
    """Structured logger for hana."""

    def __init__(self, name: str = "hana", level: LogLevel = LogLevel.INFO):
        self._logger = logging.getLogger(name)
        self._logger.setLevel(self._to_logging_level(level))
        self._logger.handlers.clear()

        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(JSONFormatter())
        self._logger.addHandler(handler)

    @staticmethod
    def _to_logging_level(level: LogLevel) -> int:
        mapping = {
            LogLevel.DEBUG: logging.DEBUG,
            LogLevel.INFO: logging.INFO,
            LogLevel.WARN: logging.WARNING,
            LogLevel.ERROR: logging.ERROR,
        }
        return mapping.get(level, logging.INFO)

    def _log(
        self,
        level: int,
        message: str,
        sku: str | None = None,
        stage: str | None = None,
        **kwargs: Any,
    ) -> None:
        extra = {}
        if sku:
            extra["sku"] = sku
        if stage:
            extra["stage"] = stage
        if kwargs:
            extra["extra_data"] = kwargs

        record = self._logger.makeRecord(
            self._logger.name,
            level,
            "",
            0,
            message,
            (),
            None,
        )
        for key, value in extra.items():
            setattr(record, key, value)

        self._logger.handle(record)

    def debug(
        self,
        message: str,
        sku: str | None = None,
        stage: str | None = None,
        **kwargs: Any,
    ) -> None:
        self._log(logging.DEBUG, message, sku, stage, **kwargs)

    def info(
        self,
        message: str,
        sku: str | None = None,
        stage: str | None = None,
        **kwargs: Any,
    ) -> None:
        self._log(logging.INFO, message, sku, stage, **kwargs)

    def warn(
        self,
        message: str,
        sku: str | None = None,
        stage: str | None = None,
        **kwargs: Any,
    ) -> None:
        self._log(logging.WARNING, message, sku, stage, **kwargs)

    def error(
        self,
        message: str,
        sku: str | None = None,
        stage: str | None = None,
        **kwargs: Any,
    ) -> None:
        self._log(logging.ERROR, message, sku, stage, **kwargs)


_logger: HanaLogger | None = None


def get_logger() -> HanaLogger:
    """Get the global logger instance."""
    global _logger
    if _logger is None:
        _logger = HanaLogger()
    return _logger


def configure_logger(level: LogLevel) -> HanaLogger:
    """Configure and return the global logger."""
    global _logger
    _logger = HanaLogger(level=level)
    return _logger
