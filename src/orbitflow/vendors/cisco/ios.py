"""Prompt-aware interactive CLI support for Cisco IOS and IOS-XE."""

from __future__ import annotations

import re
import socket
import time
from typing import Any

from orbitflow.transport import DeviceSession

_ANSI_ESCAPE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
_PROMPT = re.compile(r"(?m)^([^\r\n]+[>#])[ \t]*$")
_REJECTED_COMMAND = re.compile(
    r"(?:%\s*(?:Invalid input|Unknown command|Unrecognized command|Incomplete command)|"
    r"\^\s*$)",
    re.IGNORECASE | re.MULTILINE,
)


class CiscoIOSCLIError(Exception):
    """Base class for IOS/IOS-XE interactive CLI failures."""


class CiscoIOSCLITimeout(CiscoIOSCLIError, TimeoutError):
    """Raised when an IOS/IOS-XE prompt is not received before the deadline."""


def _normalize(text: str) -> str:
    return _ANSI_ESCAPE.sub("", text).replace("\r\n", "\n").replace("\r", "\n")


def detect_prompt(output: str) -> str | None:
    """Return a final IOS-style prompt, without assuming a hostname."""
    normalized = _normalize(output)
    matches = list(_PROMPT.finditer(normalized))
    if not matches or normalized[matches[-1].end() :].strip():
        return None
    return matches[-1].group(1).strip()


def extract_ios_hostname(prompt: str) -> str:
    """Extract the hostname from an IOS/IOS-XE exec prompt."""
    match = re.fullmatch(r"(?P<hostname>[^:#>\s]+)[#>]", prompt.strip())
    if match is None:
        raise ValueError(f"unrecognized IOS/IOS-XE prompt: {prompt!r}")
    return match.group("hostname")


def clean_output(output: str, command: str, prompt: str) -> str:
    """Remove a command echo and final prompt from channel output."""
    lines = _normalize(output).split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    command_echoes = (command.strip(), f"{prompt}{command}".strip())
    if lines and lines[0].strip() in command_echoes:
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if lines and lines[-1].strip() == prompt:
        lines.pop()
    return "\n".join(lines).strip("\n")


def _contains_command_echo(output: str, command: str, prompt: str) -> bool:
    expected_echoes = (command.strip(), f"{prompt}{command}".strip())
    return any(
        line.strip() in expected_echoes for line in _normalize(output).split("\n")
    )


class CiscoIOSCLI:
    """An IOS/IOS-XE shell layered on an established OrbitFlow session.

    The caller retains ownership of the ``DeviceSession`` and closes it.  This
    class owns only the interactive channel opened through that session.
    """

    def __init__(self, session: DeviceSession, *, timeout: float = 10.0) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        self._channel: Any = session.invoke_shell()
        try:
            self._channel.sendall(b"\n")
            _, self.prompt = self._read_until_prompt(timeout)
            setup_output = self.run_command("terminal length 0", timeout=timeout)
            if _REJECTED_COMMAND.search(setup_output):
                raise CiscoIOSCLIError(
                    "IOS/IOS-XE rejected required session setup command 'terminal length 0'"
                )
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        """Release the owned shell once; the caller still owns the session."""
        channel, self._channel = self._channel, None
        if channel is not None:
            channel.close()

    def _read_until_prompt(
        self,
        timeout: float,
        *,
        command: str | None = None,
        starting_prompt: str | None = None,
    ) -> tuple[str, str]:
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        deadline = time.monotonic() + timeout
        received = bytearray()

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CiscoIOSCLITimeout(
                    f"timed out after {timeout:g}s waiting for an IOS/IOS-XE prompt"
                )
            self._channel.settimeout(remaining)
            try:
                chunk = self._channel.recv(65535)
            except (socket.timeout, TimeoutError) as exc:
                raise CiscoIOSCLITimeout(
                    f"timed out after {timeout:g}s waiting for an IOS/IOS-XE prompt"
                ) from exc
            if not chunk:
                raise CiscoIOSCLIError(
                    "interactive channel closed before an IOS/IOS-XE prompt was received"
                )
            received.extend(chunk)
            text = received.decode("utf-8", errors="replace")
            prompt = detect_prompt(text)
            command_synchronized = command is None or _contains_command_echo(
                text, command, starting_prompt or ""
            )
            if prompt is not None and command_synchronized:
                return text, prompt

    def run_command(self, command: str, timeout: float = 10.0) -> str:
        """Run one command and return output without its echo or final prompt."""
        if not command or "\n" in command or "\r" in command:
            raise ValueError("command must be one non-empty line")
        starting_prompt = self.prompt
        self._channel.sendall((command + "\n").encode("utf-8"))
        output, prompt = self._read_until_prompt(
            timeout, command=command, starting_prompt=starting_prompt
        )
        self.prompt = prompt
        return clean_output(output, command, prompt)
