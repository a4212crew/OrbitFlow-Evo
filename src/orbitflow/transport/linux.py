"""Linux transport using tsh proxy ssh and a Paramiko direct-tcpip hop."""

from __future__ import annotations

import shlex
import shutil
from typing import Any

import paramiko

from .authentication import connect_target
from .exceptions import (
    DeviceConnectionError,
    ConnectionCleanupError,
    TeleportError,
    TransportConfigurationError,
    TunnelError,
)
from .models import DeviceCredentials, DeviceSession, TransportConfig


def _close(resource: Any | None) -> None:
    if resource is not None:
        resource.close()


def _close_all(*resources: Any | None) -> None:
    """Attempt every close even when an earlier resource raises."""
    first_error = None
    for resource in resources:
        try:
            _close(resource)
        except Exception as exc:  # cleanup must continue through all dependencies
            first_error = first_error or exc
    if first_error is not None:
        raise first_error


def connect_linux(
    device_host: str, credentials: DeviceCredentials, config: TransportConfig
) -> DeviceSession:
    """Connect to a target via a certificate-authenticated Teleport bastion."""
    if config.teleport_key_path is None or config.teleport_cert_path is None:
        raise TransportConfigurationError(
            "Linux requires teleport_key_path and teleport_cert_path from the active tsh profile"
        )
    tsh = config.tsh_path or shutil.which("tsh")
    if not tsh:
        raise TeleportError(
            "tsh was not found on PATH; install it and run tsh login first"
        )

    command = " ".join(
        shlex.quote(part)
        for part in (
            tsh,
            "proxy",
            "ssh",
            f"--cluster={config.cluster}",
            f"--proxy={config.proxy}",
            f"{config.bastion_user}@{config.bastion_host}:{config.bastion_port}",
        )
    )
    proxy = bastion = channel = target = None
    try:
        key = paramiko.PKey.from_path(str(config.teleport_key_path))
        key.load_certificate(str(config.teleport_cert_path))
        proxy = paramiko.ProxyCommand(command)
        bastion = paramiko.SSHClient()
        if config.verify_bastion_host_key:
            bastion.load_system_host_keys()
            bastion.set_missing_host_key_policy(paramiko.RejectPolicy())
        else:
            bastion.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        bastion.connect(
            config.bastion_host,
            port=config.bastion_port,
            username=config.bastion_user,
            pkey=key,
            sock=proxy,
            timeout=config.connect_timeout,
        )
    except Exception as exc:
        try:
            _close_all(bastion, proxy)
        except Exception:
            raise ConnectionCleanupError("Connection cleanup failed; retry suppressed.") from None
        raise TeleportError("failed to establish the Teleport bastion session") from exc

    try:
        transport = bastion.get_transport()
        if transport is None or not transport.is_active():
            raise TunnelError("bastion SSH transport is not active")
        channel = transport.open_channel(
            "direct-tcpip",
            (device_host, config.device_port),
            ("127.0.0.1", 0),
        )
        target = paramiko.SSHClient()
        if config.verify_device_host_key:
            target.load_system_host_keys()
            target.set_missing_host_key_policy(paramiko.RejectPolicy())
        else:
            target.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        connect_target(
            target,
            device_host,
            port=config.device_port,
            credentials=credentials,
            sock=channel,
            timeout=config.connect_timeout,
        )
    except Exception as exc:
        try:
            _close_all(target, channel, bastion, proxy)
        except Exception:
            raise ConnectionCleanupError("Connection cleanup failed; retry suppressed.") from None
        if isinstance(exc, TunnelError):
            raise
        raise DeviceConnectionError(
            f"failed to connect to target device {device_host}"
        ) from exc

    def cleanup() -> None:
        _close_all(target, channel, bastion, proxy)

    return DeviceSession(target, cleanup)
