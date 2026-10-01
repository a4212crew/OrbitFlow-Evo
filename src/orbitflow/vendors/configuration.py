"""Approved read-only full-configuration command profiles (no fallback guessing)."""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class ConfigurationProfile:
    command: str
    paging: str
    prompt: str
    rejection: str

    def rejected(self, output):
        # Only diagnostic lines at the start of a response are command errors;
        # identical strings inside a configuration/banner are ordinary content.
        return bool(re.match(self.rejection, output.lstrip(), re.I))


_CISCO = ConfigurationProfile(
    "show running-config", "terminal length 0", r"^([^\r\n]+[>#])[ \t]*$",
    r"(?:%\s*(?:Invalid|Unknown|Unrecognized|Incomplete|Ambiguous|Error|Authorization|Access denied)|\^)",
)
PROFILES = {
    "cisco_ios": _CISCO,
    "cisco_xe": _CISCO,
    "cisco_xr": _CISCO,
    "huawei_vrp": ConfigurationProfile(
        "display current-configuration", "screen-length 0 temporary",
        r"^([^\r\n]*(?:<[^<>\r\n]+>|\[[^\[\]\r\n]+\]))[ \t]*$",
        r"(?:Error:|%\s*(?:Error|Unknown)|\^)",
    ),
    "ubiquiti_edgeswitch": ConfigurationProfile(
        "show running-config", "terminal length 0", r"^([^\r\n]+[>#])[ \t]*$",
        r"(?:%\s*(?:Invalid|Unknown|Unrecognized|Incomplete|Error|Authorization)|Unrecognized command|Invalid command|\^)",
    ),
}
