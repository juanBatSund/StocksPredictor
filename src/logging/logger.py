import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.model_version import MODEL_VERSION
from config.settings import LOG_DIR

LOG_DIR.mkdir(parents=True, exist_ok=True)

_file_handler = logging.FileHandler(LOG_DIR / "system.log")
_file_handler.setFormatter(logging.Formatter("%(message)s"))

_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.setFormatter(logging.Formatter("%(message)s"))

_root = logging.getLogger("stocks")
_root.setLevel(logging.DEBUG)
_root.addHandler(_file_handler)
_root.addHandler(_console_handler)


def _emit(level: str, module: str, event: str, payload: dict[str, Any]) -> None:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model_version": MODEL_VERSION,
        "level": level,
        "module": module,
        "event": event,
        "payload": payload,
    }
    line = json.dumps(record)
    getattr(_root, level)(line)


def log_input(module: str, payload: dict[str, Any]) -> None:
    _emit("info", module, "input_received", payload)


def log_result(module: str, payload: dict[str, Any]) -> None:
    _emit("info", module, "result_produced", payload)


def log_warning(module: str, message: str, payload: dict[str, Any] | None = None) -> None:
    _emit("warning", module, message, payload or {})


def log_error(module: str, message: str, payload: dict[str, Any] | None = None) -> None:
    _emit("error", module, message, payload or {})
