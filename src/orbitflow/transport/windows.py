"""Windows transport using a validated tsh local TCP forward."""

from __future__ import annotations

import shutil
import socket
import subprocess
import time
from typing import Any

import paramiko

from .authentication import connect_target
from .exceptions import (
    DeviceConnectionError, TeleportError, TunnelError, TunnelTimeout, ConnectionCleanupError,
)
from .models import DeviceCredentials, DeviceSession, TransportConfig


def _free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _stop_process(process: Any) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _open_forwarded_socket(process: Any, port: int, timeout: float) -> socket.socket:
    """Wait for the local forward and return its first connected socket."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise TunnelError(
                "tsh local forwarding process exited before becoming ready"
            )
        try:
            remaining = max(0.001, deadline - time.monotonic())
            forwarded_socket = socket.create_connection(
                ("127.0.0.1", port), timeout=min(0.2, remaining)
            )
        except OSError:
            pass
        else:
            if process.poll() is None:
                return forwarded_socket
            forwarded_socket.close()
            raise TunnelError(
                "tsh local forwarding process exited before becoming ready"
            )
        if time.monotonic() < deadline:
            time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))
    raise TunnelTimeout("timed out waiting for the tsh local forwarding port")


def connect_windows(
    device_host: str, credentials: DeviceCredentials, config: TransportConfig
) -> DeviceSession:
    """Connect through a temporary tsh local forward on Windows."""
    tsh = config.tsh_path or shutil.which("tsh")
    if not tsh:
        raise TeleportError(
            "tsh was not found on PATH; install it and run tsh login first"
        )

    local_port = _free_local_port()
    command = [
        tsh,
        "ssh",
        "--cluster",
        config.cluster,
        "--proxy",
        config.proxy,
        "-N",
        "-L",
        f"127.0.0.1:{local_port}:{device_host}:{config.device_port}",
        f"{config.bastion_user}@{config.bastion_host}",
    ]
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise TeleportError("failed to start tsh local forwarding") from exc

    client = None
    forwarded_socket = None
    try:
        client = paramiko.SSHClient()
        if config.verify_device_host_key:
            client.load_system_host_keys()
            client.set_missing_host_key_policy(paramiko.RejectPolicy())
        else:
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        # This first successful forward connection is retained for Paramiko.
        # Reading its SSH banner here would consume protocol data Paramiko owns.
        forwarded_socket = _open_forwarded_socket(
            process, local_port, config.connect_timeout
        )
        # Keep the real device hostname as Paramiko's host-key lookup key while
        # sending traffic through the loopback forward.
        connect_target(
            client,
            device_host,
            port=config.device_port,
            credentials=credentials,
            sock=forwarded_socket,
            timeout=config.connect_timeout,
        )
    except Exception as exc:
        # Attempt every cleanup before the shared layer considers a retry.
        cleanup_failed = False
        for cleanup_resource in (lambda: client.close() if client is not None else None,
                                 lambda: forwarded_socket.close() if forwarded_socket is not None else None,
                                 lambda: _stop_process(process)):
            try:
                cleanup_resource()
            except Exception:
                cleanup_failed = True
        if cleanup_failed:
            raise ConnectionCleanupError("Connection cleanup failed; retry suppressed.") from None
        if isinstance(exc, TunnelError):
            raise
        raise DeviceConnectionError(
            f"failed to connect to target device {device_host}"
        ) from exc

    def cleanup() -> None:
        try:
            client.close()
        finally:
            try:
                if forwarded_socket is not None:
                    forwarded_socket.close()
            finally:
                _stop_process(process)

    return DeviceSession(client, cleanup)
