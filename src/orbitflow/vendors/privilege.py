"""Shared, non-logging privileged EXEC exchange for IOS/XE and EdgeSwitch."""
import codecs
import re
import time
from enum import Enum, auto



class PrivilegeError(Exception):
    """The required privileged EXEC prompt could not be established."""


class MissingEnableSecret(PrivilegeError):
    """User EXEC requires an enable credential which was not supplied."""


class EnableAuthenticationFailed(PrivilegeError):
    """Enable was rejected or did not reach the expected privileged prompt."""


class _EnableState(Enum):
    WAIT_PASSWORD = auto()
    WAIT_PRIVILEGED = auto()


def _exec_hostname(prompt):
    """Parse supported EXEC shapes without treating annotations as identity."""
    if prompt.startswith("("):
        from orbitflow.vendors.ubiquiti.prompts import extract_edgeswitch_hostname

        return extract_edgeswitch_hostname(prompt)
    match = re.fullmatch(r"([^:#<>\s()\[\]]+)[#>]", prompt)
    return match[1] if match else None


def ensure_privileged(channel, prompt, secret, timeout):
    """Recognize supported exec shapes, excluding Huawei and IOS-XR prompts.

    Never send the secret through run_command: it is not a command and its echo
    must never be returned as output. WAIT_PASSWORD accepts stale user EXEC
    prompts and command echoes; WAIT_PRIVILEGED accepts stale user EXEC prompts
    but rejects another password challenge. Neither resets the overall deadline.
    """
    from orbitflow.vendors.common import normalize_output

    hostname = _exec_hostname(prompt)
    if hostname is None:
        return prompt
    if prompt.endswith("#"):
        return prompt
    if not isinstance(secret, str) or not secret:
        raise MissingEnableSecret("Enable secret is required for privileged EXEC.")
    if "\n" in secret or "\r" in secret:
        raise EnableAuthenticationFailed("Enable authentication failed.")
    deadline = time.monotonic() + timeout
    received = ""
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    state = _EnableState.WAIT_PASSWORD
    total_received = 0
    try:
        channel.sendall(b"enable\n")
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise EnableAuthenticationFailed("Enable authentication failed.")
            channel.settimeout(remaining)
            chunk = channel.recv(65535)
            if not chunk:
                raise EnableAuthenticationFailed("Enable authentication failed.")
            total_received += len(chunk)
            if total_received > 131072:
                raise EnableAuthenticationFailed("Enable authentication failed.")
            # Discard this private exchange, including any echoed credential.
            received += decoder.decode(chunk)
            text = normalize_output(received)
            if re.search(
                r"(?im)^\s*(?:%|access denied|authentication failed|invalid password)", text
            ):
                raise EnableAuthenticationFailed("Enable authentication failed.")
            lines = text.split("\n")
            received = ""
            for index, line in enumerate(lines):
                last = line.strip()
                complete = index < len(lines) - 1
                if not last or last == secret:
                    continue
                if re.fullmatch(r"(?i)(?:enable )?password:[ \t]*", last):
                    if state is not _EnableState.WAIT_PASSWORD:
                        raise EnableAuthenticationFailed("Enable authentication failed.")
                    channel.sendall((secret + "\n").encode())
                    state = _EnableState.WAIT_PRIVILEGED
                    continue
                # Validate identity even when the prompt prefixes command echo.
                candidate = last[:-6].rstrip() if last.endswith("enable") else last
                try:
                    observed_hostname = _exec_hostname(candidate)
                except ValueError:
                    observed_hostname = None
                if observed_hostname is not None:
                    if observed_hostname != hostname:
                        raise EnableAuthenticationFailed("Enable authentication failed.")
                    if candidate.endswith("#"):
                        if state is not _EnableState.WAIT_PRIVILEGED:
                            raise EnableAuthenticationFailed("Enable authentication failed.")
                        if candidate == last and not any(part.strip() for part in lines[index + 1:]):
                            return candidate
                    # Same-host user EXEC is stale/progress material in either
                    # state, never proof of authentication failure by itself.
                    if not complete:
                        received = line
                elif complete:
                    if candidate.endswith((">", "#")) or candidate.startswith("("):
                        raise EnableAuthenticationFailed("Enable authentication failed.")
                else:
                    # Preserve partial echoes, challenges and nested annotations
                    # until another receive completes their structure.
                    received = line
    except Exception:
        # No raw exception/cause can carry the password or private response.
        raise EnableAuthenticationFailed("Enable authentication failed.") from None
