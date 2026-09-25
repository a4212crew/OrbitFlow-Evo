"""Common operating-system-independent OrbitFlow transport API."""

from __future__ import annotations

import platform

from orbitflow.logging import transport_logging

from .exceptions import (
    DeviceConnectionError,
    TeleportError,
    TransportConfigurationError,
    TransportError,
    TunnelError,
    UnsupportedPlatformError,
)
from .models import DeviceCredentials, DeviceSession, TransportConfig


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

            return connect_windows(device_host, credentials, config)
        if operating_system == "linux":
            from .linux import connect_linux

            return connect_linux(device_host, credentials, config)
        raise UnsupportedPlatformError(f"unsupported operating system: {operating_system}")


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
