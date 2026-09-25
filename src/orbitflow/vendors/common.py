"""Shared mechanics for prompt-aware vendor CLI adapters."""

from __future__ import annotations

import re
import socket
import time
from typing import Any, Callable

from orbitflow.transport import DeviceSession

_ANSI_ESCAPE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")


class InteractiveCLIError(Exception):
    """An interactive device CLI operation failed."""


class InteractiveCLITimeout(InteractiveCLIError, TimeoutError):
    """A prompt was not received before the command deadline."""


def normalize_output(text: str) -> str:
    return _ANSI_ESCAPE.sub("", text).replace("\r\n", "\n").replace("\r", "\n")


class PromptCLI:
    """Minimal prompt/echo synchronization shared by vendor-specific shells."""

    def __init__(
        self,
        session: DeviceSession,
        *,
        paging_command: str,
        prompt_pattern: str,
        rejected: Callable[[str], bool],
        platform_name: str,
        timeout: float = 10.0,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        self._prompt_re = re.compile(prompt_pattern, re.MULTILINE)
        self._rejected = rejected
        self._platform_name = platform_name
        self._channel: Any = session.invoke_shell()
        try:
            self._channel.sendall(b"\n")
            _, self.prompt = self._read_until_prompt(timeout)
            output = self.run_command(paging_command, timeout=timeout)
            if rejected(output):
                raise InteractiveCLIError(
                    f"{platform_name} rejected required session setup command {paging_command!r}"
                )
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        """Release the owned shell once; the caller still owns the session."""
        channel, self._channel = self._channel, None
        if channel is not None:
            channel.close()

    def _detect_prompt(self, output: str) -> str | None:
        normalized = normalize_output(output)
        matches = list(self._prompt_re.finditer(normalized))
        if not matches or normalized[matches[-1].end() :].strip():
            return None
        return matches[-1].group(1).strip()

    def _read_until_prompt(
        self, timeout: float, *, command: str | None = None, prompt: str = ""
    ) -> tuple[str, str]:
        deadline = time.monotonic() + timeout
        received = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise InteractiveCLITimeout(
                    f"timed out waiting for a {self._platform_name} prompt"
                )
            self._channel.settimeout(remaining)
            try:
                chunk = self._channel.recv(65535)
            except (socket.timeout, TimeoutError) as exc:
                raise InteractiveCLITimeout(
                    f"timed out waiting for a {self._platform_name} prompt"
                ) from exc
            if not chunk:
                raise InteractiveCLIError(
                    f"channel closed before a {self._platform_name} prompt was received"
                )
            received.extend(chunk)
            text = received.decode("utf-8", errors="replace")
            found = self._detect_prompt(text)
            echo = command is None or any(
                line.strip() in (command, f"{prompt}{command}")
                for line in normalize_output(text).split("\n")
            )
            if found is not None and echo:
                return text, found

    def run_command(self, command: str, timeout: float = 10.0) -> str:
        if not command or "\n" in command or "\r" in command:
            raise ValueError("command must be one non-empty line")
        starting_prompt = self.prompt
        self._channel.sendall((command + "\n").encode())
        raw, self.prompt = self._read_until_prompt(
            timeout, command=command, prompt=starting_prompt
        )
        lines = normalize_output(raw).split("\n")
        while lines and not lines[0].strip():
            lines.pop(0)
        if lines and lines[0].strip() in (command, f"{starting_prompt}{command}"):
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        if lines and lines[-1].strip() == self.prompt:
            lines.pop()
        return "\n".join(lines).strip("\n")
