"""Shared mechanics for prompt-aware vendor CLI adapters."""

from __future__ import annotations

import re
import socket
import time
from contextlib import closing, contextmanager
from typing import Any, Callable, Iterator

from orbitflow.transport import DeviceSession
from orbitflow.vendors.privilege import ensure_privileged
from orbitflow.vendors.prompts import is_structural_prompt
from orbitflow.timing import measured, device_wait

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
            if platform_name in {"identification", "Cisco", "Ubiquiti EdgeSwitch"}:
                self.prompt = ensure_privileged(
                    self._channel, self.prompt, getattr(session, "secret", None), timeout
                )
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
        prompt = matches[-1].group(1).strip()
        validate = (self._execution_prompt_validator if getattr(self, "_execution_reader", False)
                    else is_structural_prompt)
        return prompt if validate(prompt) else None

    def _read_until_prompt(
        self, timeout: float, *, command: str | None = None, prompt: str = "",
        exact_prompt: bool = False,
    ) -> tuple[str, str]:
        deadline = time.monotonic() + timeout
        received = bytearray()
        self.last_response = ''
        candidate: tuple[str, str] | None = None
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise InteractiveCLITimeout(
                    f"timed out waiting for a {self._platform_name} prompt"
                )
            self._channel.settimeout(min(remaining, 1.0) if candidate else remaining)
            try:
                with device_wait():
                    chunk = self._channel.recv(65535)
            except (socket.timeout, TimeoutError) as exc:
                if candidate is not None:
                    return candidate
                raise InteractiveCLITimeout(
                    f"timed out waiting for a {self._platform_name} prompt"
                ) from exc
            if not chunk:
                raise InteractiveCLIError(
                    f"channel closed before a {self._platform_name} prompt was received"
                )
            received.extend(chunk)
            self.last_response = received.decode('utf-8', errors='replace')
            candidate = None
            text = received.decode("utf-8", errors="replace")
            found = self._detect_prompt(text)
            echo = command is None or any(
                line.strip() in (command, f"{prompt}{command}")
                for line in normalize_output(text).split("\n")
            )
            if found is not None and echo and (not exact_prompt or found == prompt):
                if not exact_prompt:
                    if getattr(self, "_execution_reader", False):
                        # Only an unterminated final line, after the current echo,
                        # may complete a write. Quiescence protects split lines.
                        if normalize_output(text).split("\n")[-1].strip() == found:
                            candidate = (text, found)
                        continue
                    return text, found
                # A configuration line ending in a newline is body text, even
                # when identical to the exec prompt. For an unterminated match,
                # wait for receive quiescence: SSH can split within that line.
                if normalize_output(text).split("\n")[-1].strip() == prompt:
                    candidate = (text, found)

    @measured('cli_command', cli_command=True, failure='Unknown')
    def run_command(self, command: str, timeout: float = 10.0) -> str:
        if not command or "\n" in command or "\r" in command:
            raise ValueError("command must be one non-empty line")
        starting_prompt = self.prompt
        self.last_response = ''  # Never attach a prior sensitive capture to send failure.
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
    Additional required setup commands are cached after acceptance on this shell.
    This context is sequential only and never closes its parent transport.
    """

    def __init__(self, session: DeviceSession, *, timeout: float = 10.0) -> None:
        self.session = session
        self._synchronized = True
        self._completed_setup: set[str] = set()
        self._reuse_session_setup = False  # Confirmed executor opts in per shell.
        self._accepted_paging: set[tuple[str, str]] = set()
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
                  timeout: float = 10.0, setup_commands: tuple[str, ...] = ()) -> None:
        self.require_session(self.session)
        prompt_re = re.compile(prompt_pattern, re.MULTILINE)
        if not prompt_re.fullmatch(self.prompt):
            raise InteractiveCLIError("shared CLI prompt does not match selected platform")
        self._execution_reader = False
        self._prompt_re, self._rejected = prompt_re, rejected
        self._platform_name = platform_name
        paging_key = (platform_name, paging_command)
        reusable = (self._reuse_session_setup and paging_command == 'terminal length 0'
                    and platform_name in {'Cisco', 'Ubiquiti EdgeSwitch', 'cisco_ios', 'cisco_xe', 'ubiquiti_edgeswitch'})
        if not reusable or paging_key not in self._accepted_paging:
            output = self.run_command(paging_command, timeout=timeout)
            if rejected(output):
                self._accepted_paging.clear()
                raise InteractiveCLIError(
                    f"{platform_name} rejected required session setup command {paging_command!r}"
                )
            if reusable:
                self._accepted_paging.add(paging_key)

        for command in setup_commands:
            if command in self._completed_setup:
                continue
            try:
                output = self.run_command(command, timeout=timeout)
            except TimeoutError as exc:
                raise InteractiveCLITimeout(
                    f"{platform_name} timed out during required session setup {command!r}"
                ) from exc
            if rejected(output):
                self._synchronized = False
                self._accepted_paging.clear()
                raise InteractiveCLIError(
                    f"{platform_name} rejected required session setup command {command!r}"
                )
            self._completed_setup.add(command)

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
            self._accepted_paging.clear()
            raise

    @measured('configuration_read', cli_command=True, failure='Unknown')
    def read_configuration(self, command: str, timeout: float = 60.0) -> str:
        """Read sensitive text without logging, retaining whitespace/content.

        Configuration reads cannot change the exec prompt. Match that learned
        prompt exactly and allow one second of receive quiescence before
        accepting an unterminated final prompt. Newline-terminated prompt lines
        remain configuration content, including across receive boundaries.
        Only the synchronized echo and final prompt framing are removed.
        """
        self.require_session(self.session)
        if timeout <= 0 or not command or "\n" in command or "\r" in command:
            raise ValueError("invalid configuration command or timeout")
        try:
            prompt = self.prompt
            self._channel.sendall((command + "\n").encode())
            raw, _ = self._read_until_prompt(timeout, command=command,
                                             prompt=prompt, exact_prompt=True)
            lines = normalize_output(raw).split("\n")
            for index, line in enumerate(lines):
                if line.strip() in (command, f"{prompt}{command}"):
                    lines = lines[index + 1:]
                    break
            while lines and not lines[-1].strip():
                lines.pop()
            lines.pop()  # exact final prompt
            return "\n".join(lines)
        except BaseException:
            self._synchronized = False
            self._accepted_paging.clear()
            raise

    @measured('mode_validation')
    def execution_mode(self, exec_prompt: str, platform: str) -> None:
        """Select vendor structural prompts on an identified owned shell.

        Host presentation and configuration submode names may change. This
        selects framing only; command errors and independent verification still
        determine outcomes. Read-only adapters reset this execution-only reader.
        """
        self.require_session(self.session)
        if platform == 'ubiquiti_edgeswitch':
            from orbitflow.vendors.ubiquiti.configuration_execution import PROMPT, is_exec_prompt, is_execution_prompt
        elif platform in {'cisco_ios', 'cisco_xe'}:
            from orbitflow.vendors.cisco.configuration_execution import PROMPT, is_exec_prompt, is_execution_prompt
        else:
            raise InteractiveCLIError('unsupported execution platform')
        if not is_exec_prompt(exec_prompt):
            raise InteractiveCLIError('privileged EXEC required')
        selected = re.compile('^(' + PROMPT + r')[ \t]*$', re.MULTILINE)
        if not selected.fullmatch(self.prompt) or not is_execution_prompt(self.prompt):
            raise InteractiveCLIError('unexpected execution mode')
        self._prompt_re = selected
        self._execution_prompt_validator = is_execution_prompt
        self._execution_reader = True

    @measured('save_exchange', failure='Unknown')
    def save_configuration(self, exec_prompt: str, platform: str, *, timeout: float):
        """One save exchange; exact session EXEC anchor determines completion.

        The anchor must already be synchronized at privileged EXEC on this shell.
        Execution may refresh presentation after a completed sequence/recovery;
        save never learns a replacement anchor from its own response.
        Partial text is returned on failure. Never retry or answer an unknown
        question. Caller sanitizes evidence before persistence.
        """
        self.require_session(self.session)
        if self.prompt != exec_prompt or timeout <= 0:
            raise InteractiveCLIError('save requires original EXEC and positive timeout')
        self.execution_mode(exec_prompt, platform)
        raw, echoed, answered = '', False, False
        deadline = time.monotonic() + timeout
        try:
            self._channel.sendall(b'write memory\n')
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise InteractiveCLITimeout('save timeout')
                self._channel.settimeout(remaining)
                with device_wait():
                    chunk = self._channel.recv(65535)
                if not chunk:
                    raise InteractiveCLIError('save disconnected')
                raw += chunk.decode('utf-8', errors='replace')
                lines = normalize_output(raw).split('\n')
                if not echoed:
                    for index, line in enumerate(lines):
                        if line.strip() in ('write memory', exec_prompt + 'write memory'):
                            raw = '\n'.join(lines[index + 1:])
                            echoed = True
                            break
                    if not echoed:
                        continue
                text = normalize_output(raw)
                if platform == 'ubiquiti_edgeswitch' and not answered and text.rstrip().endswith('Are you sure you want to save? (y/n)'):
                    from orbitflow.progress import save_progress
                    save_progress('save_confirmation_recognized')
                    self._channel.sendall(b'y\n')
                    save_progress('save_answer_y_waiting_original_exec')
                    answered = True
                    continue
                if text.rstrip('\n').split('\n')[-1].strip() == exec_prompt:
                    return dict(status='Saved', response=text, answered=answered, error_category='')
        except BaseException as exc:
            self._synchronized = False
            self._accepted_paging.clear()
            self.last_response = normalize_output(raw)
            if not isinstance(exc, Exception):
                raise
            return dict(status='Unknown', response=normalize_output(raw), answered=answered,
                        error_category='SaveExchangeIncomplete')


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
