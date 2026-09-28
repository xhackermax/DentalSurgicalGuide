"""Logging plumbing and the 'no silent broad except' rule."""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

from dsg import dsg_logging

REPO = Path(__file__).resolve().parents[1]


def test_configure_is_idempotent_and_writes_file(tmp_path, monkeypatch):
    monkeypatch.setenv("DSG_LOG_LEVEL", "DEBUG")
    path = dsg_logging.configure(tmp_path)
    dsg_logging.configure(tmp_path)
    logger = logging.getLogger("dsg")
    tagged = [h for h in logger.handlers if getattr(h, "_dsg_handler", False)]
    assert len(tagged) == 2  # console + file, never duplicated
    try:
        raise ValueError("boom")
    except ValueError:
        logging.getLogger("dsg.test").debug("suppressed exception", exc_info=True)
    for h in tagged:
        h.flush()
    text = path.read_text("utf-8")
    assert "suppressed exception" in text and "ValueError: boom" in text
    dsg_logging.unconfigure()
    assert not [h for h in logger.handlers if getattr(h, "_dsg_handler", False)]


def test_no_silent_broad_except_pass_left():
    result = subprocess.run([sys.executable, str(REPO / "tools" / "codemod_log_suppressed.py"),
                             str(REPO / "dsg"), "--check"], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout
