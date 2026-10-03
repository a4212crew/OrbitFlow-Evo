"""Structural validation of supported CLI prompts before learning them."""
import re

# A hostname must contain identity text, not just banner punctuation. Keep
# platform selection separate: a valid prompt alone does not identify an OS.
_HOST = r"[A-Za-z0-9_.-]*[A-Za-z0-9][A-Za-z0-9_.-]*"
_CISCO_EXEC = re.compile(
    rf"(?:(?:[A-Za-z0-9_-]+/)+[A-Za-z0-9_-]+:)?{_HOST}"
    r"(?:\([A-Za-z0-9_./:-]+\))?[#>]"
)
_HUAWEI = re.compile(rf"(?:<{_HOST}>|\[[~*]?{_HOST}(?:/[A-Za-z0-9_./:-]+)?\])")


def is_structural_prompt(prompt: str) -> bool:
    """Reject decorative lines and incomplete prompts, including annotations.

    Called after the adapter's prompt pattern matches the final receive line.
    Nested EdgeSwitch annotations retain their vendor-owned parser; Cisco
    location prefixes/configuration modes and Huawei view delimiters are
    accepted without allowing arbitrary banner text before a prompt marker.
    """
    if prompt.startswith("("):
        from orbitflow.vendors.ubiquiti.prompts import extract_edgeswitch_hostname

        try:
            hostname = extract_edgeswitch_hostname(prompt)
        except ValueError:
            return False
        return re.fullmatch(_HOST, hostname) is not None
    return bool(_CISCO_EXEC.fullmatch(prompt) or _HUAWEI.fullmatch(prompt))
