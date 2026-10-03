"""Configuration and resource ownership models for device transports."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class DeviceCredentials:
    """Credentials for the target device, separate from Teleport identity."""

    username: str
    password: str | None = field(default=None, repr=False)
    pkey: Any | None = field(default=None, repr=False)
    secret: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class TransportConfig:
    """Non-secret Teleport routing settings and optional Linux identity paths."""

    proxy: str
    cluster: str
    bastion_host: str
    bastion_user: str
    teleport_key_path: Path | None = None
    teleport_cert_path: Path | None = None
    tsh_path: str | None = None
    device_port: int = 22
    bastion_port: int = 3022
    connect_timeout: float = 15.0
    verify_bastion_host_key: bool = False
    verify_device_host_key: bool = False


class DeviceSession:
    """Own an established target SSH client and all dependent resources."""

    def __init__(self, client: Any, cleanup: Callable[[], None], *, secret: str | None = None) -> None:
        self.client = client
        self._cleanup = cleanup
        self._closed = False
        self.secret = secret

    def invoke_shell(self, **kwargs: Any) -> Any:
        """Open the target's interactive shell."""
        return self.client.invoke_shell(**kwargs)

    def close(self) -> None:
        """Close all resources once, in transport-defined dependency order."""
        if not self._closed:
            self._closed = True
            self.secret = None
            self._cleanup()

    def __enter__(self) -> DeviceSession:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
