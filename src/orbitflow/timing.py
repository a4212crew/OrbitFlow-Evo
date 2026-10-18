"""Internal execution profiling; no command text, responses or exception messages.

Context variables follow the existing single-device worker, never the progress
timer. Nested spans overlap: do not sum parent and child elapsed times.
"""
from contextlib import contextmanager, ExitStack
from contextvars import ContextVar
from functools import wraps
from time import monotonic

_sink = ContextVar('execution_timing_sink', default=None)
_fields = ContextVar('execution_timing_fields', default={})
_spans = ContextVar('execution_timing_spans', default=())
_OUTCOMES = frozenset({'Completed', 'Verified', 'Failed', 'Unknown', 'Saved', 'Not required',
                       'Rejected', 'Returned', 'Not executed'})


def _result_outcome(value):
    if not isinstance(value, dict):
        return None
    status = value.get('status')
    if not isinstance(status, str):
        return None
    if status in _OUTCOMES:
        return status
    return {'present': 'Completed', 'absent': 'Completed', 'unknown': 'Unknown', 'error': 'Failed'}.get(status)


@contextmanager
def profiling(logger, clean, **fields):
    token = _sink.set((logger, clean))
    span_token = _spans.set(())
    try:
        with correlation(**fields):
            yield
    finally:
        _spans.reset(span_token)
        _sink.reset(token)


@contextmanager
def correlation(**fields):
    token = _fields.set(dict(_fields.get(), **fields))
    try:
        yield
    finally:
        _fields.reset(token)


@contextmanager
def stage(name, *, command_category='-', failure='Failed'):
    sink = _sink.get()
    if sink is None:
        yield {}
        return
    started = monotonic()
    frame = {'wait': 0.0}
    token = _spans.set((*_spans.get(), frame))
    result = {'outcome': 'Completed'}
    try:
        yield result
    except BaseException as exc:
        result['outcome'] = failure
        result['error_category'] = type(exc).__name__
        raise
    finally:
        elapsed = max(0.0, monotonic() - started)
        _spans.reset(token)
        logger, clean = sink
        fields = {k: clean(v)[:128] for k, v in _fields.get().items()
                  if k in {'run_id', 'digest', 'management_ip', 'row_id', 'template_id', 'command_index'}}
        wait = min(elapsed, frame['wait'])
        fields.update(stage=name, command_category=command_category,
                      outcome=result['outcome'] if result['outcome'] in _OUTCOMES else 'Unknown',
                      elapsed_seconds=elapsed, device_wait_seconds=wait,
                      work_seconds=max(0.0, elapsed - wait))
        if 'error_category' in result:
            fields['error_category'] = clean(result['error_category'])[:128]
        logger.info('Execution timing', extra=fields)


@contextmanager
def device_wait():
    """Measure blocking receive time, including prompt quiescence/timeouts.

    Work time is residual wall time, not CPU time; connection and scheduler waits
    are separate stages and are not misrepresented as measured device receives.
    """
    frames = _spans.get()
    if not frames:
        yield
        return
    started = monotonic()
    try:
        yield
    finally:
        elapsed = max(0.0, monotonic() - started)
        for frame in frames:
            frame['wait'] += elapsed


def command_category(command):
    """Only fixed categories escape this boundary, never literal CLI/arguments."""
    if not isinstance(command, str):
        return 'approved_or_other'  # Original API retains invalid-input handling.
    if command in {'terminal length 0', 'terminal width 511', 'terminal length 0 all', 'no page'}:
        return 'session_setup'
    if command.startswith(('show running-config', 'display current-configuration')):
        return 'configuration_read'
    if command.startswith('show vlan'):
        return 'vlan_read'
    if command.startswith('show interfaces'):
        return 'interface_read'
    if command in {'end', 'exit', 'configure', 'configure terminal', 'vlan database'}:
        return 'mode'
    return 'approved_or_other'


def measured(name, *, cli_command=False, failure='Failed'):
    def decorate(function):
        @wraps(function)
        def call(*args, **kwargs):
            category = command_category(args[1] if len(args) > 1 else kwargs.get('command')) if cli_command else '-'
            with stage(name, command_category=category, failure=failure) as result:
                value = function(*args, **kwargs)
                outcome = _result_outcome(value)
                if outcome is not None:
                    result['outcome'] = outcome
                return value
        return call
    return decorate


def timed_call(name, function, *args, **kwargs):
    with stage(name, failure='Unknown' if name in {'approved_command', 'mode_recovery_command', 'device_save', 'post_row_verification'} else 'Failed') as result:
        value = function(*args, **kwargs)
        outcome = _result_outcome(value)
        if outcome is not None:
            result['outcome'] = outcome
        return value


@contextmanager
def timed_context(name, manager):
    """Time resource establishment separately from its lifetime and cleanup."""
    with ExitStack() as stack:
        with stage(name):
            value = stack.enter_context(manager())
        yield value
