"""Common operating-system-independent OrbitFlow transport API."""

from __future__ import annotations

import platform

from orbitflow.logging import transport_logging

from .exceptions import (
    DeviceConnectionError,
    ConnectionRetryExhausted,
    TeleportError,
    TransportConfigurationError,
    TransportError,
    TunnelError,
    UnsupportedPlatformError,
)
from .models import DeviceCredentials, DeviceSession, TransportConfig
from .policy import (
    wait_for_connection_start, retryable_connection_failure, wait_before_connection_retry,
)


def connect_device(
    device_host: str,
    credentials: DeviceCredentials,
    config: TransportConfig,
    *,
    system: str | None = None,
) -> DeviceSession:
    """Connect to a device using the validated transport for the current OS."""
    with transport_logging(device_host):
        operating_system = (system or platform.system()).lower()
        if operating_system == "windows":
            from .windows import connect_windows

            connector = connect_windows
        elif operating_system == "linux":
            from .linux import connect_linux

            connector = connect_linux
        else:
            raise UnsupportedPlatformError(f"unsupported operating system: {operating_system}")
        for attempt in range(2):
            wait_for_connection_start()
            try:
                session = connector(device_host, credentials, config)
            except Exception as exc:
                if not retryable_connection_failure(exc):
                    raise
                if attempt:
                    raise ConnectionRetryExhausted(
                        "Transient connection failure after two attempts."
                    ) from exc
                # OS connectors finish cleanup before raising; cleanup failures
                # are non-retryable. The next attempt still acquires a start slot.
                wait_before_connection_retry()
            else:
                session.secret = credentials.secret
                return session


__all__ = [
    "DeviceConnectionError",
    "DeviceCredentials",
    "DeviceSession",
    "TeleportError",
    "TransportConfig",
    "TransportConfigurationError",
    "TransportError",
    "TunnelError",
    "UnsupportedPlatformError",
    "connect_device",
]
