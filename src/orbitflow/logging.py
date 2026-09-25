"""Shared file logging. Never pass credentials or raw device output to a logger.

Exception diagnostics deliberately retain types, errno and frame locations rather
than arbitrary exception messages, source lines or locals (all may hold secrets).
"""

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re

_root = ContextVar("orbitflow_log_root", default=Path("logs"))
MAX_BYTES = 2 * 1024 * 1024
BACKUP_COUNT = 3


def sanitize_text(value):
    """Sanitize scalar text for operational output without stringifying objects."""
    if not isinstance(value, (str, int, float, bool)):
        return "[REDACTED]"
    text = str(value)
    text = re.sub(r"-----BEGIN .*?PRIVATE KEY-----.*", "[REDACTED]", text, flags=re.S)
    return re.sub(
        r"(?i)(password|passwd|otp|token|secret|authorization|pkey|private_key|credentials)\s*['\"]?\s*[:=]\s*.*",
        r"\1=[REDACTED]", text, flags=re.S,
    )


def _safe(value):
    return sanitize_text(value)[:4096]


class SafeFormatter(logging.Formatter):
    def format(self, record):
        # Do not stringify arbitrary objects, including credential dataclasses.
        message = _safe(record.msg)
        if record.args:
            message += " [arguments omitted]"
        data = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "management_ip": _safe(getattr(record, "management_ip", "-")),
            "error_category": _safe(getattr(record, "error_category", "-")),
            "message": message,
        }
        if record.exc_info and record.exc_info[1]:
            diagnostics = []
            exc = record.exc_info[1]
            seen = set()
            while exc is not None and id(exc) not in seen:
                seen.add(id(exc))
                frames = []
                tb = exc.__traceback__
                while tb is not None:
                    frames.append({"file": Path(tb.tb_frame.f_code.co_filename).name,
                                   "line": tb.tb_lineno,
                                   "function": tb.tb_frame.f_code.co_name})
                    tb = tb.tb_next
                diagnostics.append({"category": type(exc).__name__,
                                    "errno": exc.errno if isinstance(exc, OSError) else None,
                                    "frames": frames})
                exc = exc.__cause__ or (None if exc.__suppress_context__ else exc.__context__)
            data["exception_chain"] = diagnostics
        return json.dumps(data, ensure_ascii=True)


@contextmanager
def module_logger(module, filename=None, *, log_root=None):
    """Own one bounded log writer; usable by inventory, transport or future modules.

    Dates are UTC run dates. Each file has three backups; historical date folders
    are retained for operator archival. Callers must not share files across processes.
    """
    filename = filename or module
    if not all(re.fullmatch(r"[a-zA-Z0-9_-]+", part) for part in (module, filename)):
        raise ValueError("log module and filename must be simple names")
    root = Path(log_root) if log_root is not None else _root.get()
    path = root / module / datetime.now(timezone.utc).date().isoformat() / (filename + ".log")
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT,
                                  encoding="utf-8")
    handler.setFormatter(SafeFormatter())
    logger = logging.Logger(f"orbitflow.{module}", logging.DEBUG)
    logger.propagate = False
    logger.addHandler(handler)
    token = _root.set(root)
    try:
        yield logger, path
    finally:
        _root.reset(token)
        handler.close()
        logger.removeHandler(handler)


class _DependencyHandler(logging.Handler):
    def __init__(self, logger, management_ip):
        super().__init__(logging.WARNING)
        self.logger = logger
        self.management_ip = management_ip

    def emit(self, record):
        # Paramiko emits traceback lines as plain strings. Never forward those
        # strings: they can contain arbitrary authentication data or source code.
        self.logger.log(record.levelno, "SSH dependency diagnostic (raw text omitted)",
                        extra={"management_ip": self.management_ip,
                               "error_category": "SSHDiagnostic"})


@contextmanager
def transport_logging(management_ip):
    """Capture connection diagnostics without changing SSH or exception semantics.

    Paramiko routing is process-wide for this scope; intended for sequential runs.
    Restore the application's logging configuration even on connection failure.
    """
    with module_logger("transport") as (logger, _):
        dependency = logging.getLogger("paramiko")
        previous = dependency.handlers[:], dependency.propagate, dependency.level
        dependency.handlers = [_DependencyHandler(logger, management_ip)]
        dependency.propagate = False
        dependency.setLevel(logging.WARNING)
        try:
            yield
        except Exception as exc:
            logger.error("Device connection failed", exc_info=True,
                         extra={"management_ip": management_ip,
                                "error_category": type(exc).__name__})
            raise
        finally:
            dependency.handlers, dependency.propagate, dependency.level = previous
