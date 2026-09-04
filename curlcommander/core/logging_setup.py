"""Logging with secret redaction (3.7).

--log-file / --log-level configure a logger whose every record passes through a
RedactingFilter that scrubs common credential patterns (Bearer tokens, Basic
``-u`` values, API-key/Cookie headers) so a debug log never becomes a token
dump --- the same principle as the history redaction.
"""

from __future__ import annotations

import logging
import re

_PATTERNS = [
    (re.compile(r"(?i)(authorization:\s*bearer\s+)\S+"), r"\1«REDACTED»"),
    (re.compile(r"(?i)(authorization:\s*basic\s+)\S+"), r"\1«REDACTED»"),
    (re.compile(r"(?i)(-u\s+)\S+"), r"\1«REDACTED»"),
    (re.compile(r"(?i)(cookie:\s*)[^\n]+"), r"\1«REDACTED»"),
    (re.compile(r"(?i)(x-api-key:\s*)\S+"), r"\1«REDACTED»"),
    (re.compile(r"(?i)(set-cookie:\s*)[^\n]+"), r"\1«REDACTED»"),
]

LOGGER_NAME = "curlcommander"


def redact_log(text: str) -> str:
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_log(record.msg)
        if record.args:
            record.args = tuple(redact_log(a) if isinstance(a, str) else a for a in record.args)
        return True


def setup_logging(log_file: str | None, log_level: str | None) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    logger.handlers.clear()
    level = getattr(logging, (log_level or "WARNING").upper(), logging.WARNING)
    logger.setLevel(level)

    handler: logging.Handler = logging.FileHandler(log_file) if log_file else logging.NullHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    handler.addFilter(RedactingFilter())
    logger.addHandler(handler)
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)
