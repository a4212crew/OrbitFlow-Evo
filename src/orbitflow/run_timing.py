"""Payload-free monotonic workflow timings using existing rotating module logs."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from inspect import signature
import sys
from time import monotonic
from uuid import uuid4
from orbitflow.logging import module_logger

current_log_root = ContextVar('orbitflow_timing_log_root', default=None)


def _log_root(function, args, kwargs):
    if kwargs.get('log_root') is not None:
        return kwargs['log_root']
    bound = signature(function).bind_partial(*args, **kwargs).arguments
    if bound.get('log_root') is not None:
        return bound['log_root']
    if function.__name__ == 'main' and 'argv' in signature(function).parameters:
        argv = bound.get('argv')
        argv = sys.argv[1:] if argv is None else argv
        root = None
        for index, value in enumerate(argv):
            if value == '--':
                break
            if value == '--log-root' and index + 1 < len(argv):
                root = argv[index + 1]
            elif value.startswith('--log-root='):
                root = value.split('=', 1)[1]
        if root is not None:
            return root
    return current_log_root.get()


current_run = ContextVar('orbitflow_timing_run', default=None)


def new_run_id(*, short=False):
    if short:
        return datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_') + uuid4().hex[:8]
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ_') + uuid4().hex


def timed(stage):
    """Time an actual function boundary; nested phases share the owning run ID.

    Durations may enclose child phases and are therefore not additive. Only
    log_root/CLI --log-root is inspected for routing and inherited by children;
    argument values, return values and exception messages are never logged.
    """
    def decorate(function):
        @wraps(function)
        def invoke(*args, **kwargs):
            root = _log_root(function, args, kwargs)
            root_token = current_log_root.set(root)
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
                with module_logger(module, log_root=root) as (logger, _):
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
                current_log_root.reset(root_token)
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
