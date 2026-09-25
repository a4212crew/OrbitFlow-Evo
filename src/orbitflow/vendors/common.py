"""Shared mechanics for prompt-aware vendor CLI adapters."""

from __future__ import annotations

import re
import socket
import time
from contextlib import closing, contextmanager
from typing import Any, Callable, Iterator

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
        # Ignore stale prompt/receive data preceding the synchronized echo.
        for index, line in enumerate(lines):
            if line.strip() in (command, f"{starting_prompt}{command}"):
                lines = lines[index + 1:]
                break
        while lines and not lines[-1].strip():
            lines.pop()
        if lines and lines[-1].strip() == self.prompt:
            lines.pop()
        return "\n".join(lines).strip("\n")


class DeviceCLI(PromptCLI):
    """One caller-owned shell for sequential capabilities on one DeviceSession.

    Start with the inventory probe's permissive prompt/setup behavior. Vendor
    adapters then select their existing prompt and paging rules on this same
    reader. A failed exchange invalidates synchronization; subsequent commands
    fail locally rather than consuming a late response as a new command result.
    This context is sequential only and never closes its parent transport.
    """

    def __init__(self, session: DeviceSession, *, timeout: float = 10.0) -> None:
        self.session = session
        self._synchronized = True
        # Huawei safely rejects this initial inventory probe setup; its
        # approved paging command is selected during identification.
        super().__init__(session, paging_command="terminal length 0",
                         prompt_pattern=r"^([^\r\n]+(?:#|>|\]))[ \t]*$",
                         rejected=lambda _: False, platform_name="identification",
                         timeout=timeout)

    def __enter__(self) -> DeviceCLI:
        self.require_session(self.session)
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def require_session(self, session: DeviceSession) -> None:
        if session is not self.session:
            raise ValueError("CLI belongs to a different DeviceSession")
        if self._channel is None or not self._synchronized:
            raise InteractiveCLIError("shared CLI is closed or unsynchronized")

    def configure(self, *, paging_command: str, prompt_pattern: str,
                  rejected: Callable[[str], bool], platform_name: str,
                  timeout: float = 10.0) -> None:
        self.require_session(self.session)
        prompt_re = re.compile(prompt_pattern, re.MULTILINE)
        if not prompt_re.fullmatch(self.prompt):
            raise InteractiveCLIError("shared CLI prompt does not match selected platform")
        self._prompt_re, self._rejected = prompt_re, rejected
        self._platform_name = platform_name
        output = self.run_command(paging_command, timeout=timeout)
        if rejected(output):
            raise InteractiveCLIError(
                f"{platform_name} rejected required session setup command {paging_command!r}"
            )

    def run_command(self, command: str, timeout: float = 10.0) -> str:
        self.require_session(self.session)
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        if not command or "\n" in command or "\r" in command:
            raise ValueError("command must be one non-empty line")
        try:
            return super().run_command(command, timeout=timeout)
        except BaseException:
            self._synchronized = False
            raise


@contextmanager
def open_prompt_cli(
    session: DeviceSession, *, cli: DeviceCLI | None = None, **behavior
) -> Iterator[PromptCLI]:
    """Borrow the workflow shell, or own a temporary standalone vendor shell."""
    if cli is not None:
        cli.require_session(session)
        cli.configure(**behavior)
        yield cli
    else:
        with closing(PromptCLI(session, **behavior)) as temporary:
            yield temporary
