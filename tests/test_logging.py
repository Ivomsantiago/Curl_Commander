"""Tests for 3.7 logging with secret redaction."""

import logging

from curlcommander.core.logging_setup import redact_log, setup_logging


def test_redact_log_scrubs_secrets():
    assert "«REDACTED»" in redact_log("Authorization: Bearer abc.def.ghi")
    assert "supersecret" not in redact_log("Cookie: session=supersecret")
    assert "u:p" not in redact_log("curl -u u:p https://x")


def test_setup_logging_writes_redacted_file(tmp_path):
    log = tmp_path / "cc.log"
    logger = setup_logging(str(log), "info")
    logger.info("request with Authorization: Bearer TOPSECRET")
    for h in logger.handlers:
        h.flush()
    contents = log.read_text()
    assert "TOPSECRET" not in contents
    assert "«REDACTED»" in contents


def test_default_level_is_quiet(tmp_path):
    logger = setup_logging(None, None)
    assert logger.level == logging.WARNING
