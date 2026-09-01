from __future__ import annotations

import builtins
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict

from app.infrastructure.observability.context import current_log_context


_ORIGINAL_PRINT = builtins.print
_ORIGINAL_STDOUT = sys.stdout
_ORIGINAL_STDERR = sys.stderr
_CONFIGURED = False

RESERVED_LOG_RECORD_ATTRS = set(logging.makeLogRecord({}).__dict__.keys()) | {
    "message",
    "asctime",
}


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in current_log_context().items():
            if not hasattr(record, key):
                setattr(record, key, value)
        return True


class JsonLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = _sanitize_text(record.getMessage())
        payload: Dict[str, Any] = {
            "ts": _format_ts(record.created),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", None) or message.split(" ", 1)[0],
            "message": message,
        }
        for key, value in record.__dict__.items():
            if key in RESERVED_LOG_RECORD_ATTRS or key.startswith("_"):
                continue
            if key in {"args", "exc_info", "exc_text", "stack_info", "msg"}:
                continue
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            payload[key] = _json_safe(value)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class PrettyFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": "\033[90m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[41;97m",
    }
    RESET = "\033[0m"
    DIM = "\033[2m"
    CYAN = "\033[36m"

    def __init__(self, *, color: bool) -> None:
        super().__init__()
        self._color = bool(color)

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S.%f")[:-3]
        level = record.levelname
        event = str(getattr(record, "event", "") or "")
        message = _sanitize_text(record.getMessage())
        context_bits = []
        for key in ("request_id", "session_id", "trace_id", "run_id", "node_id"):
            value = getattr(record, key, None)
            if value:
                context_bits.append(f"{key}={_short(value)}")
        extra = " ".join(context_bits)
        name = record.name[-36:]
        line = f"{ts} {level:<7} {name:<36} {event:<28} {message}"
        if extra:
            line = f"{line} {extra}"
        if record.exc_info:
            line = f"{line}\n{self.formatException(record.exc_info)}"
        if not self._color:
            return line
        color = self.COLORS.get(level, "")
        exception_text = f"\n{self.formatException(record.exc_info)}" if record.exc_info else ""
        if extra:
            line = line.replace(extra, f"{self.CYAN}{extra}{self.RESET}")
        return f"{self.DIM}{ts}{self.RESET} {color}{level:<7}{self.RESET} {name:<36} {event:<28} {message}" + (
            f" {self.CYAN}{extra}{self.RESET}" if extra else ""
        ) + exception_text


def configure_logging(settings: Any | None = None) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    level = str(getattr(settings, "LOG_LEVEL", None) or os.getenv("LOG_LEVEL") or "INFO").upper()
    log_file_enabled = _as_bool(getattr(settings, "LOG_FILE_ENABLED", None), default=False)
    log_file_path = str(getattr(settings, "LOG_FILE_PATH", None) or os.getenv("LOG_FILE_PATH") or "backend.log")
    log_file_format = str(getattr(settings, "LOG_FILE_FORMAT", None) or os.getenv("LOG_FILE_FORMAT") or "json").lower()
    console_pretty = _as_bool(getattr(settings, "LOG_CONSOLE_PRETTY", None), default=True)
    capture_prints = _as_bool(getattr(settings, "LOG_CAPTURE_PRINTS", None), default=True)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(getattr(logging, level, logging.INFO))

    context_filter = ContextFilter()
    console = logging.StreamHandler(_ORIGINAL_STDOUT)
    console.setLevel(getattr(logging, level, logging.INFO))
    console.addFilter(context_filter)
    console.setFormatter(PrettyFormatter(color=console_pretty))
    root.addHandler(console)

    if log_file_enabled:
        path = Path(log_file_path)
        if not path.is_absolute():
            path = Path.cwd() / path
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(path, maxBytes=20 * 1024 * 1024, backupCount=5, encoding="utf-8")
        file_handler.setLevel(getattr(logging, level, logging.INFO))
        file_handler.addFilter(context_filter)
        file_handler.setFormatter(JsonLineFormatter() if log_file_format == "json" else PrettyFormatter(color=False))
        root.addHandler(file_handler)

    logging.captureWarnings(True)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "app"):
        logger = logging.getLogger(name)
        logger.setLevel(getattr(logging, level, logging.INFO))
        logger.propagate = True

    if capture_prints:
        _install_print_capture()


def _install_print_capture() -> None:
    if getattr(builtins.print, "__name__", "") == "_structured_print":
        return

    def _structured_print(*args: Any, **kwargs: Any) -> None:
        try:
            sep = kwargs.get("sep", " ")
            end = kwargs.get("end", "\n")
            file = kwargs.get("file")
            if file is not None and file not in {_ORIGINAL_STDOUT, _ORIGINAL_STDERR, sys.stdout, sys.stderr}:
                _ORIGINAL_PRINT(*args, **kwargs)
                return
            message = sep.join(str(arg) for arg in args)
            if end and end != "\n":
                message = f"{message}{end}"
            logger = logging.getLogger("app.stdout" if file is not _ORIGINAL_STDERR else "app.stderr")
            level = logging.ERROR if file is _ORIGINAL_STDERR else logging.INFO
            logger.log(level, message, extra={"event": "stdout.print"})
        except Exception:
            _ORIGINAL_PRINT(*args, **kwargs)

    builtins.print = _structured_print


def log_print(*args: Any, **kwargs: Any) -> None:
    try:
        sep = kwargs.get("sep", " ")
        end = kwargs.get("end", "\n")
        file = kwargs.get("file")
        if file is not None and file not in {_ORIGINAL_STDOUT, _ORIGINAL_STDERR, sys.stdout, sys.stderr}:
            _ORIGINAL_PRINT(*args, **kwargs)
            return
        message = sep.join(str(arg) for arg in args)
        if end and end != "\n":
            message = f"{message}{end}"
        logger = logging.getLogger("app.stdout" if file is not _ORIGINAL_STDERR else "app.stderr")
        level = logging.ERROR if file is _ORIGINAL_STDERR else logging.INFO
        logger.log(level, message, extra={"event": "stdout.print"})
    except Exception:
        _ORIGINAL_PRINT(*args, **kwargs)


def restore_print_for_tests() -> None:
    builtins.print = _ORIGINAL_PRINT


def _format_ts(created: float) -> str:
    return datetime.fromtimestamp(created, tz=timezone.utc).astimezone().isoformat(timespec="milliseconds")


def _json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)):
        return _sanitize_text(value) if isinstance(value, str) else value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in list(value.items())[:80]}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in list(value)[:80]]
    return _sanitize_text(str(value))


_SENSITIVE_QUERY_KEYS = (
    "Signature",
    "OSSAccessKeyId",
    "Expires",
    "x-oss-signature",
    "x-oss-credential",
    "x-oss-date",
    "x-oss-security-token",
)
_SENSITIVE_QUERY_PATTERN = re.compile(
    r"([?&])(" + "|".join(re.escape(k) for k in _SENSITIVE_QUERY_KEYS) + r")=([^&\\s\"]+)",
    flags=re.IGNORECASE,
)


def _sanitize_text(text: str) -> str:
    raw = str(text or "")
    if not raw:
        return raw
    return _SENSITIVE_QUERY_PATTERN.sub(lambda m: f"{m.group(1)}{m.group(2)}=<redacted>", raw)


def _short(value: Any) -> str:
    text = str(value)
    if len(text) <= 16:
        return text
    return text[:12]


def _as_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return str(os.getenv("", "")).lower() == "true" if False else default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "debug", "pretty"}
