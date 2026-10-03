import socket

import pytest

from orbitflow.transport import DeviceSession
from orbitflow.vendors.cisco import (
    CiscoIOSCLI,
    CiscoIOSCLITimeout,
    clean_output,
    detect_prompt,
)


class FakeChannel:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.sent = []
        self.timeouts = []

    def sendall(self, data):
        self.sent.append(data)

    def settimeout(self, timeout):
        self.timeouts.append(timeout)

    def recv(self, _size):
        response = next(self.responses)
        if isinstance(response, BaseException):
            raise response
        return response


def make_session(channel):
    class Client:
        def invoke_shell(self, **_kwargs):
            return channel

    return DeviceSession(Client(), lambda: None)


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("Welcome\r\nedge-router-01#", "edge-router-01#"),
        ("switch-a>", "switch-a>"),
        ("router(config-if)#   \r\n", "router(config-if)#"),
        ("show clock\r\n12:00:00 UTC\r\n", None),
    ],
)
def test_detect_prompt_supports_privileged_and_unprivileged_prompts(output, expected):
    assert detect_prompt(output) == expected


def test_command_execution_disables_paging_and_tracks_changed_prompt():
    channel = FakeChannel(
        [
            b"Banner\r\nrouter#",
            b"terminal length 0\r\nrouter#",
            b"show version\r\nCisco IOS XE Software, Version 17.12\r\nrouter-new#",
        ]
    )
    cli = CiscoIOSCLI(make_session(channel), timeout=2)

    result = cli.run_command("show version", timeout=4)

    assert channel.sent == [b"\n", b"terminal length 0\n", b"show version\n"]
    assert result == "Cisco IOS XE Software, Version 17.12"
    assert cli.prompt == "router-new#"
    assert channel.timeouts and all(timeout > 0 for timeout in channel.timeouts)


def test_command_execution_ignores_stale_prompt_before_command_echo():
    channel = FakeChannel(
        [
            b"router#",
            b"router#",
            b"terminal length 0\r\nrouter#",
            b"show version\r\nCisco IOS Software\r\nrouter#",
        ]
    )
    cli = CiscoIOSCLI(make_session(channel))

    assert cli.run_command("show version") == "Cisco IOS Software"


def test_command_timeout_is_reported_without_fixed_sleeping():
    channel = FakeChannel(
        [b"router#", b"terminal length 0\r\nrouter#", socket.timeout()]
    )
    cli = CiscoIOSCLI(make_session(channel))

    with pytest.raises(CiscoIOSCLITimeout, match="waiting for an IOS/IOS-XE prompt"):
        cli.run_command("show interfaces", timeout=0.25)

    assert channel.timeouts[-1] <= 0.25


def test_clean_output_removes_echo_prompt_and_terminal_control_sequences():
    raw = "\x1b[2Kshow clock\r\r\n*12:34:56.000 UTC Sun Sep 20 2026\r\nrouter#\r\n"

    assert clean_output(raw, "show clock", "router#") == (
        "*12:34:56.000 UTC Sun Sep 20 2026"
    )


def test_clean_output_removes_prompt_prefixed_command_echo():
    raw = "router#show version\r\nCisco IOS Software\r\nrouter#"

    assert clean_output(raw, "show version", "router#") == "Cisco IOS Software"
