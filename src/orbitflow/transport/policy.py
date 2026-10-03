"""Connection-start admission, independent of active device worker ownership."""
from contextvars import ContextVar
import errno
from threading import Lock
import time

from paramiko import AuthenticationException, BadHostKeyException
from paramiko.ssh_exception import NoValidConnectionsError

from .exceptions import (
    DeviceConnectionError, TeleportError, TunnelError,
    TransportConfigurationError, UnsupportedPlatformError,
    TransientSSHHandshakeError,
)


class ConnectionStartPacer:
    """Serialize only start slots, never hold a lock across device connections."""
    def __init__(self, interval, *, clock=None, sleep=None):
        self.interval = interval
        self._clock = clock or time.monotonic
        self._sleep = sleep or time.sleep
        self._lock = Lock()
        self._last = None

    def wait(self):
        with self._lock:
            if self._last is not None:
                remaining = self._last + self.interval - self._clock()
                if remaining > 0:
                    self._sleep(remaining)
            self._last = self._clock()


connection_pacer = ContextVar("connection_pacer", default=None)
_default_pacer = ConnectionStartPacer(0.25)


def wait_for_connection_start():
    (connection_pacer.get() or _default_pacer).wait()


def retryable_connection_failure(error):
    """Allow only typed transient connect failures, never message heuristics.

    Inspect explicit transport causes only. CLI/workflow errors cannot qualify
    even if they wrap a timeout. Authentication and host-key failures veto retry.
    """
    if isinstance(error, (AuthenticationException, BadHostKeyException,
                          TransportConfigurationError, UnsupportedPlatformError)):
        return False
    if isinstance(error, TransientSSHHandshakeError):
        return True
    if isinstance(error, NoValidConnectionsError):
        return bool(error.errors) and all(retryable_connection_failure(item)
                                         for item in error.errors.values())
    if isinstance(error, (DeviceConnectionError, TeleportError, TunnelError)):
        seen = set()
        while isinstance(error, (DeviceConnectionError, TeleportError, TunnelError)):
            if isinstance(error, TransientSSHHandshakeError):
                return True
            if id(error) in seen:
                return False
            seen.add(id(error))
            if isinstance(error, TimeoutError):
                return True
            error = error.__cause__
        return retryable_connection_failure(error)
    # Exact built-in types exclude command/CLI timeout subclasses.
    if type(error) in (TimeoutError, ConnectionResetError, ConnectionAbortedError,
                       ConnectionRefusedError):
        return True
    return type(error) is OSError and error.errno in {
        errno.ETIMEDOUT, errno.ECONNRESET, errno.ECONNABORTED, errno.ECONNREFUSED,
    }
