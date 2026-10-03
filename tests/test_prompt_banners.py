"""Login banners must never become the shared shell's learned prompt."""
from contextlib import closing
import re
import socket

import pytest

from orbitflow.inventory import DeviceInventoryResolver, JsonInventoryStore
from orbitflow.vendors.common import DeviceCLI, InteractiveCLITimeout
from orbitflow.vendors.cisco.ios import CiscoIOSCLI, CiscoIOSCLITimeout, detect_prompt
from orbitflow.vendors.prompts import is_structural_prompt
from test_capability_context import DEVICES
from test_device_access import ACCESS_DEVICES, SECRET, enable_session
from test_shared_cli import device_session


BANNER = b"#########################################\r\n# Authorized access only #\r\n#########################################\r\n"


def banner_chunks(prompt, layout):
    payload = BANNER + prompt.encode()
    if layout == "combined":
        return [payload]
    if layout == "lines":
        return BANNER.splitlines(keepends=True) + ([prompt.encode()] if prompt else [])
    # Includes boundaries within a separator, before its newline, and within
    # the actual prompt (including annotation text containing # and >).
    return [bytes([byte]) for byte in payload]


def add_login_banner(channel, layout):
    send = channel.sendall

    def send_with_banner(data):
        send(data)
        if data == b"\n":
            channel.pending = banner_chunks(channel.prompt, layout)

    channel.sendall = send_with_banner


@pytest.mark.parametrize("prompt", [
    "r-site-01#", "r-site-01>", "switch_a.example#", "123#",
    "router(config-if)#", "RP/0/RP0/CPU0:router#",
    "RP/0/RSP0/CPU0:router(config)#", "<vrp-router>", "[vrp-router]",
    "[~vrp-router]", "[*vrp-router-GigabitEthernet0/0/1]",
    "(switch) >", "(switch) #", "(switch (arbitrary (nested) # > text)) >",
    "(switch (arbitrary (nested) # > text)) #",
])
def test_supported_prompt_structure(prompt):
    assert is_structural_prompt(prompt)


@pytest.mark.parametrize("prompt", [
    "#", "#########################################", ">>>>>>", "]]]]]]",
    "----------#", "**********>", "==== # ==== #", "# Authorized access only #",
    "Welcome to this device >", "(---) #", "<--->", "[***]",
    "(switch (annotation #", "(switch (annotation >", "(switch annotation) #",
    "(switch (x))) #", "router##", "<router]", "[router>",
])
def test_decorative_or_malformed_lines_are_not_prompts(prompt):
    assert not is_structural_prompt(prompt)
    assert detect_prompt(prompt) is None
    # Exercise the actual shared detector, with its broad adapter pattern.
    cli = DeviceCLI.__new__(DeviceCLI)
    cli._prompt_re = re.compile(r"^([^\r\n]+(?:#|>|\]))[ \t]*$", re.MULTILINE)
    assert cli._detect_prompt(prompt) is None


@pytest.mark.parametrize("layout", ["combined", "lines", "bytes"])
@pytest.mark.parametrize("device", DEVICES, ids=lambda d: d[2])
@pytest.mark.parametrize("shared", [False, True])
def test_inventory_learns_real_prompt_after_login_banner(tmp_path, device, layout, shared):
    session, client, channel = device_session(device)
    if device[1] == "ubiquiti_edgeswitch":
        channel.prompt = "(sw (arbitrary (nested) # > text)) #"
    add_login_banner(channel, layout)
    resolver = DeviceInventoryResolver(JsonInventoryStore(tmp_path / "inventory.json"))
    with session:
        if shared:
            with DeviceCLI(session) as cli:
                assert cli.prompt == channel.prompt
                context = resolver.resolve(session, management_ip="192.0.2.1", cli=cli)
                assert cli.prompt == channel.prompt
        else:
            context = resolver.resolve(session, management_ip="192.0.2.1")
        assert context.platform == device[1]
        assert context.hostname.startswith("sw")
        assert "show version" in channel.sent
        assert not channel.pending
    assert (client.opens, client.closes, channel.close_calls) == (1, 1, 1)


@pytest.mark.parametrize("cli_type", [DeviceCLI, CiscoIOSCLI])
@pytest.mark.parametrize("layout", ["combined", "lines", "bytes"])
def test_command_echo_sync_ignores_banner_separators(cli_type, layout):
    session, client, channel = device_session(DEVICES[0])
    add_login_banner(channel, layout)
    send = channel.sendall

    def send_with_command_banner(data):
        send(data)
        if data == b"show version\n":
            # The fake channel already inserts a stale prompt and split echo.
            channel.pending[2:2] = banner_chunks("", layout)
            if cli_type is CiscoIOSCLI:
                # Standalone Cisco cleanup removes a leading command echo;
                # stale-data stripping belongs to the shared DeviceCLI.
                channel.pending.pop(0)

    channel.sendall = send_with_command_banner
    with session, closing(cli_type(session)) as cli:
        assert cli.prompt == "sw#"
        output = cli.run_command("show version")
        assert output == BANNER.decode().replace("\r\n", "\n") + DEVICES[0][0]
        assert cli.prompt == "sw#"
        assert not channel.pending
    assert (client.opens, client.closes, channel.close_calls) == (1, 1, 1)


@pytest.mark.parametrize("device", ACCESS_DEVICES, ids=lambda d: d[2])
@pytest.mark.parametrize("layout", ["combined", "lines", "bytes"])
def test_user_exec_banner_preserves_enable_flow(device, layout):
    session, client, channel = enable_session(device)
    add_login_banner(channel, layout)
    with session, DeviceCLI(session) as cli:
        assert cli.prompt == channel.prompt
        assert cli.prompt.endswith("#")
        assert cli.run_command("show version") == device[0]
        assert channel.sent[:4] == ["", "enable", SECRET, "terminal length 0"]
        assert not channel.pending
    assert client.closes == channel.close_calls == 1
    assert session.secret is None


@pytest.mark.parametrize("cli_type,error", [
    (DeviceCLI, InteractiveCLITimeout), (CiscoIOSCLI, CiscoIOSCLITimeout),
])
def test_banner_without_prompt_times_out_and_cleans_up(cli_type, error):
    session, client, channel = device_session(DEVICES[0])
    send = channel.sendall

    def banner_only(data):
        send(data)
        if data == b"\n":
            channel.pending = [BANNER, socket.timeout()]

    channel.sendall = banner_only
    with pytest.raises(error), session:
        cli_type(session)
    assert channel.sent == [""]
    assert client.closes == channel.close_calls == 1
