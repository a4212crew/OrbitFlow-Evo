"""Shared target-device SSH authentication helpers."""

from __future__ import annotations

from typing import Any

import paramiko

from .models import DeviceCredentials
from .exceptions import TransientSSHHandshakeError


def _lost_handshake_session(client: Any, error: Exception) -> bool:
    """Recognize Paramiko's specific key-retrieval race, not arbitrary SSH errors.

    Traceback provenance prevents matching a server message or host-key policy
    failure. A recorded protocol/authentication failure vetoes this classification.
    The classified error exposes only a fixed safe message.
    """
    if type(error) is not paramiko.SSHException or error.args != ("No existing session",):
        return False
    trace = error.__traceback__
    while trace is not None:
        if trace.tb_frame.f_code is paramiko.Transport.get_remote_server_key.__code__:
            transport = client.get_transport()
            if transport is None:
                return False
            underlying = transport.get_exception()
            return underlying is None or type(underlying) in (
                EOFError, TimeoutError, ConnectionResetError, ConnectionAbortedError,
            )
        trace = trace.tb_next
    return False


def _password_interactive_handler(password: str):
    """Build a handler that supplies the password only to password prompts."""

    def handler(
        _title: str, _instructions: str, prompts: list[tuple[str, bool]]
    ) -> list[str]:
        if not prompts or any(
            "password" not in prompt.lower() for prompt, _ in prompts
        ):
            raise paramiko.AuthenticationException(
                "keyboard-interactive requested a non-password response"
            )
        return [password for _prompt, _echo in prompts]

    return handler


def connect_target(
    client: Any,
    device_host: str,
    credentials: DeviceCredentials,
    **connect_kwargs: Any,
) -> None:
    """Connect with normal auth, then retry a rejected password interactively."""
    password_error: paramiko.AuthenticationException | None = None
    try:
        client.connect(
            device_host,
            username=credentials.username,
            password=credentials.password,
            pkey=credentials.pkey,
            **connect_kwargs,
        )
        return
    except paramiko.AuthenticationException as exc:
        password_error = exc
        if credentials.password is None:
            raise
        allowed_types = getattr(password_error, "allowed_types", None)
        if allowed_types is not None and "keyboard-interactive" not in allowed_types:
            raise
    except paramiko.SSHException as exc:
        if _lost_handshake_session(client, exc):
            raise TransientSSHHandshakeError("SSH session lost during handshake.") from None
        raise

    transport = client.get_transport()
    if transport is None or not transport.is_active():
        assert password_error is not None
        raise password_error
    transport.auth_interactive(
        credentials.username,
        _password_interactive_handler(credentials.password),
    )
