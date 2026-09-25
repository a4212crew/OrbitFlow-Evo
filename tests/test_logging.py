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
    assert caught.value is error
    assert (dependency.handlers, dependency.propagate, dependency.level) == previous
    assert not capsys.readouterr().err
    path = next((tmp_path / "transport").glob("*/transport.log"))
    text = path.read_text()
    assert "synthetic-password" not in text
    assert "synthetic-token" not in text
    records = [json.loads(line) for line in text.splitlines()]
    assert records[-1]["management_ip"] == "192.0.2.1"
    assert records[-1]["error_category"] == "DeviceConnectionError"
    assert records[-1]["exception_chain"][1]["category"] == "TimeoutError"
