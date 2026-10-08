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
from threading import RLock

_root = ContextVar("orbitflow_log_root", default=Path("outputs/logs"))
MAX_BYTES = 2 * 1024 * 1024
BACKUP_COUNT = 3
_writers_lock = RLock()
_writers = {}
_dependency_lock = RLock()
_dependency_users = 0
_dependency_previous = {}
_dependency_handler = None
_dependency_sinks = ()
_active_dependency_loggers = []
_code_root = Path(__file__).resolve().parents[2]


def _frame_location(tb):
    """Only repository code locations are diagnostic data, never caller paths."""
    code = tb.tb_frame.f_code
    try:
        relative = Path(code.co_filename).resolve().relative_to(_code_root)
    except (ValueError, OSError):
        relative = None
    if relative is not None and relative.parts[0] in {'src', 'scripts'}:
        return {'file': relative.as_posix(), 'line': tb.tb_lineno,
                'function': code.co_name}
    return {'file': '[external]', 'line': tb.tb_lineno, 'function': '[omitted]'}


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
            pending = [exc]
            while pending:
                exc = pending.pop()
                if id(exc) in seen:
                    continue
                seen.add(id(exc))
                frames = []
                tb = exc.__traceback__
                while tb is not None:
                    frames.append(_frame_location(tb))
                    tb = tb.tb_next
                diagnostics.append({"category": type(exc).__name__,
                                    "errno": exc.errno if isinstance(exc, OSError) else None,
                                    "frames": frames})
                secondary = getattr(exc, 'spool_state_error', None)
                if isinstance(secondary, BaseException):
                    pending.append(secondary)
                cause = exc.__cause__ or (None if exc.__suppress_context__ else exc.__context__)
                if cause is not None:
                    pending.append(cause)
            data["exception_chain"] = diagnostics
        return json.dumps(data, ensure_ascii=True)


def log_run_failure(exc, *, log_root=None):
    """Log outside device scopes; never let logging replace the original failure."""
    try:
        with module_logger('application', 'run_errors', log_root=log_root) as (logger, _):
            logger.error('Run-level application/persistence/export failure',
                         exc_info=(type(exc), exc, exc.__traceback__),
                         extra={'error_category': type(exc).__name__, 'run_diagnostic': True})
        return True
    except Exception:
        return False


class _SafeRotatingFileHandler(RotatingFileHandler):
    def handleError(self, record):
        if getattr(record, 'run_diagnostic', False):
            # The caller reports a fixed fallback; logging's default handler
            # would otherwise print a raw filesystem traceback to stderr.
            raise
        super().handleError(record)


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
    writer_key = path.resolve()
    with _writers_lock:
        if writer_key not in _writers:
            handler = _SafeRotatingFileHandler(path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT,
                                          encoding="utf-8")
            handler.setFormatter(SafeFormatter())
            _writers[writer_key] = [handler, 0]
        handler, users = _writers[writer_key]
        _writers[writer_key][1] = users + 1
    logger = logging.Logger(f"orbitflow.{module}", logging.DEBUG)
    logger.propagate = False
    logger.addHandler(handler)
    token = _root.set(root)
    try:
        yield logger, path
    finally:
        _root.reset(token)
        logger.removeHandler(handler)
        with _writers_lock:
            _writers[writer_key][1] -= 1
            if _writers[writer_key][1] == 0:
                del _writers[writer_key]
                handler.close()


class _DependencyHandler(logging.Handler):
    def emit(self, record):
        # Paramiko's own threads have no caller context. Emit once per active
        # destination, without guessing which device produced an internal line.
        with _dependency_lock:
            for logger in _dependency_sinks:
                logger.log(record.levelno, "SSH dependency diagnostic (raw text omitted)",
                           extra={"management_ip": "-", "error_category": "SSHDiagnostic"})


@contextmanager
def transport_logging(management_ip):
    """Route global dependency diagnostics until the last overlapping scope exits.

    Only logging setup/teardown is locked; connections remain concurrent. Existing
    child configuration is restored exactly. New ordinary children inherit the
    protected parent. Raw dependency text is never forwarded.
    """
    global _dependency_users, _dependency_handler, _dependency_sinks
    with module_logger("transport") as (logger, _):
        with _dependency_lock:
            if _dependency_users == 0:
                _dependency_handler = _DependencyHandler(logging.WARNING)
            dependencies = [logging.getLogger("paramiko")] + [
                child for name, child in list(logging.Logger.manager.loggerDict.items())
                if name.startswith("paramiko.") and isinstance(child, logging.Logger)
            ]
            for child in dependencies:
                if child not in _dependency_previous:
                    _dependency_previous[child] = (child.handlers[:], child.propagate, child.level)
                    child.handlers = [_dependency_handler]
                    child.propagate = False
                    child.setLevel(logging.WARNING)
            _dependency_users += 1
            # Keep one logger per file, with scoped owners tracked separately.
            _active_dependency_loggers.append(logger)
            _dependency_sinks = tuple({id(item.handlers[0]): item
                                       for item in _active_dependency_loggers}.values())
        try:
            yield
        except Exception as exc:
            logger.error("Device connection failed", exc_info=True,
                         extra={"management_ip": management_ip,
                                "error_category": type(exc).__name__})
            raise
        finally:
            with _dependency_lock:
                _active_dependency_loggers.remove(logger)
                _dependency_sinks = tuple({id(item.handlers[0]): item
                                           for item in _active_dependency_loggers}.values())
                _dependency_users -= 1
                if _dependency_users == 0:
                    for child, (handlers, propagate, level) in _dependency_previous.items():
                        child.handlers = handlers
                        child.propagate = propagate
                        child.setLevel(level)
                    _dependency_previous.clear()
                    _dependency_handler.close()
                    _dependency_handler = None
