"""Shared, non-logging privileged EXEC exchange for IOS/XE and EdgeSwitch."""
import re
import time



class PrivilegeError(Exception):
    """The required privileged EXEC prompt could not be established."""


class MissingEnableSecret(PrivilegeError):
    """User EXEC requires an enable credential which was not supplied."""


class EnableAuthenticationFailed(PrivilegeError):
    """Enable was rejected or did not reach the expected privileged prompt."""


def ensure_privileged(channel, prompt, secret, timeout):
    """Recognize supported exec shapes, excluding Huawei and IOS-XR prompts.

    Never send the secret through run_command: it is not a command and its echo
    must never be returned as output. One password response is allowed.
    """
    from orbitflow.vendors.common import normalize_output

    if prompt.startswith("("):
        from orbitflow.vendors.ubiquiti.prompts import extract_edgeswitch_hostname

        extract_edgeswitch_hostname(prompt)  # malformed annotation fails closed
    elif not re.fullmatch(r"[^:#<>\s()\[\]]+[#>]", prompt):
        return prompt
    if prompt.endswith("#"):
        return prompt
    if not isinstance(secret, str) or not secret:
        raise MissingEnableSecret("Enable secret is required for privileged EXEC.")
    if "\n" in secret or "\r" in secret:
        raise EnableAuthenticationFailed("Enable authentication failed.")
    expected = prompt[:-1] + "#"
    deadline = time.monotonic() + timeout
    received = bytearray()
    answered = False
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
            received.extend(chunk)
            # Discard this private exchange, including any echoed credential.
            text = normalize_output(received.decode("utf-8", errors="replace"))
            last = text.split("\n")[-1].strip()
            if last == expected:
                return expected
            if re.search(r"(?i)(?:^|\n)[ \t]*(?:enable )?password:[ \t]*$", text):
                if answered:
                    raise EnableAuthenticationFailed("Enable authentication failed.")
                channel.sendall((secret + "\n").encode())
                answered = True
                received.clear()
            elif last == prompt or re.search(
                r"(?im)^\s*(?:%|access denied|authentication failed|invalid password)", text
            ):
                raise EnableAuthenticationFailed("Enable authentication failed.")
    except Exception:
        # No raw exception/cause can carry the password or private response.
        raise EnableAuthenticationFailed("Enable authentication failed.") from None
