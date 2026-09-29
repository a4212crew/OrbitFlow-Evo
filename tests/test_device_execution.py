"""Coordinated concurrency tests: no live devices or timing-based sleeps."""
from contextvars import ContextVar
from threading import Barrier, Event, Lock, Thread, get_ident

import pytest

from orbitflow.config import ExecutionConfig, load_execution_config
from orbitflow.execution import execute_devices


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "10", None])
def test_invalid_limits(value):
    with pytest.raises(ValueError, match="positive integer"):
        ExecutionConfig(value)


def test_configuration(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert load_execution_config().max_concurrent_devices == 10
    (tmp_path / "orbitflow.toml").write_text("[execution]\nmax_concurrent_devices = 3\n")
    assert load_execution_config() == ExecutionConfig(3)
    with pytest.raises(FileNotFoundError):
        load_execution_config(tmp_path / "missing.toml")


@pytest.mark.parametrize("limit", [2, 10])
def test_bound_refill_failures_order_and_context(limit, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    release = Event()
    first_wave = Barrier(limit)
    refilled = Event()
    lock = Lock()
    active = peak = 0
    context = ContextVar("test_context", default="missing")
    token = context.set("inherited")
    results = []

    def worker(index):
        nonlocal active, peak
        assert context.get() == "inherited"
        context.set(str(index))
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            if index < limit:
                first_wave.wait(timeout=10)
            if index == 0:
                assert release.wait(10)
            elif index == 1:
                raise RuntimeError("synthetic-secret")
            elif index == limit:
                refilled.set()
            return index
        finally:
            with lock:
                active -= 1

    # Run the coordinator in the caller's copied context, as production does.
    from contextvars import copy_context
    def run():
        results.extend(execute_devices(range(limit * 3), worker, config=ExecutionConfig(limit) if limit != 10 else None))
    thread = Thread(target=copy_context().run, args=(run,))
    thread.start()
    try:
        assert refilled.wait(10), "pending device must start while device zero is blocked"
        assert active >= 1
    finally:
        release.set()
        thread.join(15)
        context.reset(token)
    assert not thread.is_alive()
    assert peak == limit
    assert active == 0
    assert [item.position for item in results] == list(range(1, limit * 3 + 1))
    assert results[1].error_category == "RuntimeError"
    assert "synthetic-secret" not in repr(results)
    assert [item.value for item in results if not item.error_category] == [i for i in range(limit * 3) if i != 1]


def test_limit_one_is_sequential_and_failure_isolated():
    caller = get_ident()
    seen = []
    context = ContextVar("sequential_context", default="original")
    def worker(target):
        assert get_ident() == caller
        assert context.get() == "original"
        context.set("worker mutation")
        seen.append(target)
        if target == 1:
            raise ValueError("private")
        return target
    outcomes = execute_devices(range(4), worker, config=ExecutionConfig(1))
    assert seen == list(range(4))
    assert outcomes[1].error_category == "ValueError"
    assert outcomes[3].value == 3
    assert execute_devices([], worker) == []
