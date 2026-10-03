"""Transport-specific exceptions exposed by OrbitFlow."""


class TransportError(Exception):
    """Base class for failures while establishing or using a transport."""


class UnsupportedPlatformError(TransportError):
    """Raised when the execution operating system is unsupported."""


class TransportConfigurationError(TransportError):
    """Raised when required, non-secret transport settings are missing."""


class TeleportError(TransportError):
    """Raised when a Teleport command or credential is unavailable."""


class TunnelError(TransportError):
    """Raised when a tunnel or forwarding channel cannot be opened."""


class DeviceConnectionError(TransportError):
    """Raised when SSH connection to the target device fails."""


class ConnectionRetryExhausted(DeviceConnectionError):
    """Both approved transient connection attempts failed."""


class TransientSSHHandshakeError(DeviceConnectionError):
    """SSH session disappeared during initial remote-server-key retrieval."""


class TunnelTimeout(TunnelError, TimeoutError):
    """The local forwarding socket did not become ready within its deadline."""


class ConnectionCleanupError(TransportError):
    """Failed-start cleanup was incomplete; starting another attempt is unsafe."""
