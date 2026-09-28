"""Central logging configuration for DSG (single responsibility: log plumbing).

* Every DSG module logs through ``logging.getLogger(__name__)`` (``dsg.*``).
* ``configure()`` attaches one rotating file handler under Blender's USER
  scripts directory (``…/scripts/dsg_logs/dsg.log``) and a console handler for
  warnings. It is idempotent: re-registering the add-on never duplicates
  handlers.
* Exceptions that DSG deliberately tolerates are logged at DEBUG with a full
  traceback instead of being silently discarded. Set the environment variable
  ``DSG_LOG_LEVEL=DEBUG`` (or call ``set_level("DEBUG")``) to record them.

No ``bpy`` import at module level so it can be used by workers and tests.
"""
from __future__ import annotations

import logging as _dsg_logging
_DSG_LOG = _dsg_logging.getLogger(__name__)

import logging
import logging.handlers
import os
from pathlib import Path

ROOT_LOGGER = "dsg"
_HANDLER_TAG = "_dsg_handler"
_FORMAT = "%(asctime)s %(levelname)-7s %(name)s:%(lineno)d  %(message)s"


def default_log_dir() -> Path:
    override = os.environ.get("DSG_LOG_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    try:
        import bpy
        base = bpy.utils.user_resource("SCRIPTS")
        if base:
            return Path(base) / "dsg_logs"
    except Exception:  # noqa: BLE001 - outside Blender
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    return Path.home() / ".dsg" / "logs"


def _level_from_env(default: int) -> int:
    name = os.environ.get("DSG_LOG_LEVEL", "").strip().upper()
    return getattr(logging, name, default) if name else default


def configure(log_dir: str | os.PathLike | None = None, *, level: int = logging.INFO) -> Path | None:
    """Attach DSG handlers once. Returns the log file path (None if unwritable)."""
    logger = logging.getLogger(ROOT_LOGGER)
    logger.setLevel(_level_from_env(level))
    logger.propagate = False
    unconfigure()
    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    console.setFormatter(logging.Formatter("[DSG] %(levelname)s %(name)s: %(message)s"))
    setattr(console, _HANDLER_TAG, True)
    logger.addHandler(console)
    try:
        directory = Path(log_dir) if log_dir else default_log_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "dsg.log"
        handler = logging.handlers.RotatingFileHandler(path, maxBytes=5 * 1024 * 1024, backupCount=3,
                                                       encoding="utf-8")
        handler.setFormatter(logging.Formatter(_FORMAT))
        setattr(handler, _HANDLER_TAG, True)
        logger.addHandler(handler)
        return path
    except OSError as exc:
        logger.warning("DSG file logging disabled: %s", exc)
        return None


def unconfigure() -> None:
    logger = logging.getLogger(ROOT_LOGGER)
    for handler in list(logger.handlers):
        if getattr(handler, _HANDLER_TAG, False):
            logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:  # noqa: BLE001
                _DSG_LOG.debug("suppressed exception", exc_info=True)


def set_level(level: str | int) -> None:
    logging.getLogger(ROOT_LOGGER).setLevel(getattr(logging, str(level).upper(), level)
                                            if isinstance(level, str) else level)


def log_file() -> Path | None:
    for handler in logging.getLogger(ROOT_LOGGER).handlers:
        if isinstance(handler, logging.FileHandler) and getattr(handler, _HANDLER_TAG, False):
            return Path(handler.baseFilename)
    return None
