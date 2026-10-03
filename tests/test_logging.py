from datetime import datetime, timezone
import errno
import json
import logging

import pytest

from orbitflow.logging import BACKUP_COUNT, MAX_BYTES, module_logger
from orbitflow.transport import DeviceConnectionError, DeviceCredentials, TransportConfig, connect_device


def test_paths_metadata_rotation_and_closed_handlers(tmp_path):
    with module_logger("inventory", "inventory_batch", log_root=tmp_path) as (logger, path):
        assert path == tmp_path / "inventory" / datetime.now(timezone.utc).date().isoformat() / "inventory_batch.log"
        handler = logger.handlers[0]
        assert handler.maxBytes == MAX_BYTES
        assert handler.backupCount == BACKUP_COUNT
        logger.info("Completed", extra={"management_ip": "192.0.2.1"})
        record = json.loads(path.read_text())
        assert record["module"] == "orbitflow.inventory"
        assert record["level"] == "INFO"
        assert record["management_ip"] == "192.0.2.1"
        assert record["error_category"] == "-"
        assert datetime.fromisoformat(record["timestamp"]).tzinfo is not None
        handler.maxBytes = 300
        for _ in range(30):
            logger.info("Bounded file test")
        assert len(list(path.parent.glob("inventory_batch.log*"))) == BACKUP_COUNT + 1
    assert not logger.handlers
    assert handler.stream is None


def test_sanitization_omits_objects_arguments_and_exception_values(tmp_path):
    secret = "synthetic-sensitive-value"
    with module_logger("vlans", log_root=tmp_path) as (logger, path):
        logger.info(DeviceCredentials("user", secret))
        logger.info("credentials: %s", DeviceCredentials("user", secret))
        logger.info("token=" + secret)
        logger.info("-----BEGIN OPENSSH PRIVATE KEY-----\n" + secret)
        try:
            try:
                raise OSError(errno.ECONNREFUSED, secret)
            except OSError as exc:
                raise DeviceConnectionError(secret) from exc
        except DeviceConnectionError:
            logger.exception("Connection failed")
        text = path.read_text()
        assert secret not in text
        records = [json.loads(line) for line in text.splitlines()]
        chain = records[-1]["exception_chain"]
        assert [item["category"] for item in chain] == ["DeviceConnectionError", "ConnectionRefusedError"]
        assert chain[1]["errno"] == errno.ECONNREFUSED
        assert chain[0]["frames"]


@pytest.mark.parametrize("name", ["../transport", "a/b", "a\\b", ""])
def test_rejects_path_traversal(tmp_path, name):
    with pytest.raises(ValueError):
        with module_logger(name, log_root=tmp_path):
            pass


@pytest.mark.parametrize("system", ["windows", "linux"])
def test_transport_captures_dependency_noise_and_preserves_exception(tmp_path, monkeypatch, capsys, system):
    from orbitflow.transport import linux, windows

    error = DeviceConnectionError("password=synthetic-password")

    def fail(*args):
        logging.getLogger("paramiko.transport").error("Traceback: token=synthetic-token")
        try:
            raise TimeoutError("synthetic-password")
        except TimeoutError as cause:
            raise error from cause

    monkeypatch.setattr(windows if system == "windows" else linux, "connect_" + system, fail)
    dependency = logging.getLogger("paramiko")
    previous = dependency.handlers[:], dependency.propagate, dependency.level
    with module_logger("inventory", log_root=tmp_path):
        with pytest.raises(DeviceConnectionError) as caught:
            connect_device("192.0.2.1", DeviceCredentials("user", "synthetic-password"),
                           TransportConfig("proxy", "cluster", "bastion", "user"), system=system)
    assert caught.value.__cause__ is error
    assert (dependency.handlers, dependency.propagate, dependency.level) == previous
    assert not capsys.readouterr().err
    path = next((tmp_path / "transport").glob("*/transport.log"))
    text = path.read_text()
    assert "synthetic-password" not in text
    assert "synthetic-token" not in text
    records = [json.loads(line) for line in text.splitlines()]
    assert records[-1]["management_ip"] == "192.0.2.1"
    assert records[-1]["error_category"] == "ConnectionRetryExhausted"
    assert records[-1]["exception_chain"][2]["category"] == "TimeoutError"


def test_overlapping_connections_restore_only_after_last_exit(tmp_path, capsys):
    from threading import Event, Thread
    from orbitflow.execution import execute_devices
    from orbitflow.config import ExecutionConfig
    from orbitflow.logging import transport_logging

    entered = Event()
    first_left = Event()
    child = logging.getLogger("paramiko.concurrent_test")
    original = child.handlers[:], child.propagate, child.level
    console = logging.StreamHandler()
    child.handlers = [console]
    child.propagate = False
    child.setLevel(logging.DEBUG)
    previous = child.handlers[:], child.propagate, child.level

    def worker(index):
        if index == 0:
            with transport_logging("192.0.2.1"):
                assert entered.wait(10)
            first_left.set()
        else:
            with transport_logging("192.0.2.2"):
                entered.set()
                assert first_left.wait(10)
                assert child.handlers != previous[0]
                # Real Paramiko emits on its own threads, without contextvars.
                thread = Thread(target=lambda: child.error("password=synthetic-overlap-secret"))
                thread.start()
                thread.join(10)
                assert not thread.is_alive()
                logging.getLogger("paramiko.new_child").error("synthetic-overlap-secret")
                raise DeviceConnectionError("synthetic-overlap-secret")
    try:
        with module_logger("inventory", log_root=tmp_path):
            outcomes = execute_devices([0, 1], worker, config=ExecutionConfig(2))
        assert not outcomes[0].error_category
        assert outcomes[1].error_category == "DeviceConnectionError"
        assert (child.handlers, child.propagate, child.level) == previous
        assert not capsys.readouterr().err
        text = next((tmp_path / "transport").glob("*/transport.log")).read_text()
        assert "synthetic-overlap-secret" not in text
        assert text.count("SSH dependency diagnostic") == 2
        assert "192.0.2.2" in text
    finally:
        child.handlers, child.propagate, child.level = original
        console.close()


def test_concurrent_log_writers_share_rotation_handler(tmp_path):
    from threading import Barrier
    from orbitflow.execution import execute_devices
    from orbitflow.config import ExecutionConfig
    barrier = Barrier(4)
    handlers = []
    def worker(index):
        with module_logger("transport", log_root=tmp_path) as (logger, path):
            handler = logger.handlers[0]
            handlers.append(handler)
            barrier.wait(timeout=10)
            for _ in range(10):
                logger.info("Concurrent diagnostic")
            barrier.wait(timeout=10)
            return path
    outcomes = execute_devices(range(4), worker, config=ExecutionConfig(4))
    assert all(not item.error_category for item in outcomes)
    assert len({id(handler) for handler in handlers}) == 1
    assert handlers[0].stream is None
    records = [json.loads(line) for line in outcomes[0].value.read_text().splitlines()]
    assert len(records) == 40
