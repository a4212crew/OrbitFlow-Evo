"""Conservative Cisco terminal echo framing; never interpret response bodies."""
import re

from orbitflow.vendors.common import command_echo_end, normalize_output

_EVC = re.compile(r"show ethernet service (instance id [0-9]+ interface [A-Za-z][A-Za-z0-9/-]+ detail)")


def cisco_echo_end(text: str, command: str, prompt: str) -> int | None:
    full = command_echo_end(text, command, prompt)
    if full is not None:
        return full
    lines = normalize_output(text).split("\n")
    index = 0
    while index < len(lines) - 1 and lines[index].strip() in ("", prompt):
        index += 1
    if index >= len(lines) - 1:
        return None
    first = lines[index]
    # Cisco's '$' marks left clipping. Require the learned prompt and the
    # entire distinguishing EVC target, never an arbitrary command suffix.
    target = _EVC.fullmatch(command)
    clipped = first.startswith(prompt + "$ ")
    if clipped:
        if target is None:
            return None
        expected = target.group(1)
        fragment = first[len(prompt + "$ "):]
    else:
        expected = command
        fragment = first[len(prompt):] if first.startswith(prompt) else first
    # Wrapping must concatenate exactly; do not trim away spaces or consume
    # body lines after the command. Incomplete final lines await another read.
    for end in range(index + 1, len(lines)):
        if fragment == expected:
            return end
        if not fragment or not expected.startswith(fragment):
            return None
        if end >= len(lines) - 1:
            return None
        fragment += lines[end]
    return None
