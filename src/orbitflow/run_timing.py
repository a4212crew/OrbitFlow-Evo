"""Payload-free monotonic workflow timings using existing rotating module logs."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from time import monotonic
from uuid import uuid4
from orbitflow.logging import module_logger

current_run = ContextVar('orbitflow_timing_run', default=None)


def new_run_id(*, short=False):
    if short:
        return datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_') + uuid4().hex[:8]
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ_') + uuid4().hex


def timed(stage):
    """Time an actual function boundary; nested phases share the owning run ID.

    Durations may enclose child phases and are therefore not additive. Never
    inspect function arguments, return values or exception messages for logs.
    """
    def decorate(function):
        @wraps(function)
        def invoke(*args, **kwargs):
            token = None
            if current_run.get() is None:
                token = current_run.set(new_run_id())
            identity = getattr(function, '__module__', 'orbitflow.execution')
            if not isinstance(identity, str):
                identity = 'orbitflow.execution'
            if identity == '__main__':
                namespace = function.__globals__
                identity = getattr(namespace.get('__spec__'), 'name', None) or Path(namespace.get('__file__', 'workflow')).stem
            module = identity.split('.')[-1]
            started = datetime.now(timezone.utc).isoformat()
            tick, status = monotonic(), 'success'
            from orbitflow.terminal_progress import current_position
            metadata = dict(run_id=current_run.get(), workflow=identity, stage=stage,
                            started_at=started, input_position=current_position.get())
            try:
                with module_logger(module, log_root=kwargs.get('log_root')) as (logger, _):
                    logger.info('stage_start', extra=metadata)
                    try:
                        return function(*args, **kwargs)
                    except BaseException as exc:
                        status = 'interrupted' if isinstance(exc, KeyboardInterrupt) else 'failure'
                        metadata['error_category'] = type(exc).__name__
                        raise
                    finally:
                        logger.info('stage_end', extra=dict(metadata, ended_at=datetime.now(timezone.utc).isoformat(),
                                    elapsed_seconds=round(monotonic()-tick, 3), status=status))
            finally:
                if token is not None:
                    current_run.reset(token)
        return invoke
    return decorate


@contextmanager
def run_scope(identity):
    """Correlate a selected durable run, restoring the caller even on failure."""
    token = current_run.set(identity)
    try:
        yield
    finally:
        current_run.reset(token)
