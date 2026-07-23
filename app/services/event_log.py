"""In-memory event log for full on-screen observability.

Every notable thing the backend does (API calls, retries, model fallbacks,
JSON repairs, pipeline stages, errors with tracebacks) is recorded here and
served to the frontend via /api/events so it can be shown live in the UI.

This is a personal app: nothing is redacted on purpose.
"""

import itertools
import logging
import threading
import time
import traceback

_lock = threading.Lock()
_events: list[dict] = []
_seq = itertools.count(1)

MAX_EVENTS = 3000

# Logger names that would flood the console with noise (HTTP access logs for
# the polling endpoint itself, etc.)
_IGNORED_LOGGERS = ("uvicorn.access",)


def log_event(stage: str, message: str, level: str = "info", detail: str = "") -> dict:
    """Record an event. Levels: info | warn | error | retry | success | api."""
    event = {
        "seq": next(_seq),
        "ts": time.time(),
        "level": level,
        "stage": stage,
        "message": message,
        "detail": detail or "",
    }
    with _lock:
        _events.append(event)
        if len(_events) > MAX_EVENTS:
            del _events[: len(_events) - MAX_EVENTS]
    return event


def get_events(since: int = 0) -> list[dict]:
    """Return all events with seq > since (oldest first)."""
    with _lock:
        return [e for e in _events if e["seq"] > since]


def clear_events() -> None:
    with _lock:
        _events.clear()


class Timer:
    """Tiny helper to log a stage with its duration.

    with Timer("pdf", "Generating PDF"):
        ...
    """

    def __init__(self, stage: str, message: str):
        self.stage = stage
        self.message = message
        self.start = 0.0

    def __enter__(self):
        self.start = time.perf_counter()
        log_event(self.stage, f"{self.message}…")
        return self

    def __exit__(self, exc_type, exc, tb):
        elapsed = time.perf_counter() - self.start
        if exc_type is None:
            log_event(self.stage, f"{self.message} — done in {elapsed:.1f}s", level="success")
        else:
            log_event(
                self.stage,
                f"{self.message} — FAILED after {elapsed:.1f}s: {exc_type.__name__}: {exc}",
                level="error",
                detail="".join(traceback.format_exception(exc_type, exc, tb)),
            )
        return False


class EventLogHandler(logging.Handler):
    """Mirror every Python logging record (any module: app, tenacity, google,
    anthropic, openai…) into the event log, including full tracebacks."""

    _LEVEL_MAP = {
        "DEBUG": None,  # skipped
        "INFO": "info",
        "WARNING": "warn",
        "ERROR": "error",
        "CRITICAL": "error",
    }

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if record.name.startswith(_IGNORED_LOGGERS):
                return
            level = self._LEVEL_MAP.get(record.levelname, "info")
            if level is None:
                return
            detail = ""
            if record.exc_info and record.exc_info[0] is not None:
                detail = "".join(traceback.format_exception(*record.exc_info))
            # Short module path as the stage, e.g. "app.services.ai_adapter" -> "ai_adapter"
            stage = record.name.rsplit(".", 1)[-1]
            log_event(stage, record.getMessage(), level=level, detail=detail)
        except Exception:
            # The log mirror must never break the app.
            pass


def install_logging_bridge() -> None:
    """Attach the handler to the root logger exactly once."""
    root = logging.getLogger()
    if any(isinstance(h, EventLogHandler) for h in root.handlers):
        return
    handler = EventLogHandler(level=logging.INFO)
    root.addHandler(handler)
