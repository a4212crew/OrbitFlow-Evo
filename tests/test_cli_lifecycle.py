"""Capability shells are released while their caller-owned session stays usable."""
from contextlib import closing
import socket

import pytest

from orbitflow.capabilities import (
    InterfaceCapabilityError, InterfaceService, VlanCapabilityError, VlanService,
)
from orbitflow.inventory import DeviceInventoryError, DeviceInventoryResolver, JsonInventoryStore
from orbitflow.transport import DeviceSession
from orbitflow.vendors.common import PromptCLI, InteractiveCLIError
from orbitflow.vendors.cisco.ios import CiscoIOSCLI, CiscoIOSCLIError
from orbitflow.vendors.cisco.interfaces import CiscoXRCLI
from test_capability_context import DEVICES
from test_interface_capability import CASES as INTERFACES
from test_vlan_capability import CASES as VLANS


class Channel:
    def __init__(self, prompt, outputs, *, send_failure=False):
        self.prompt, self.outputs = prompt, outputs
        self.send_failure = send_failure
        self.command = ""
        self.close_calls = 0

    def sendall(self, data):
        assert not self.close_calls
        if self.send_failure:
            raise OSError("send failed")
        self.command = data.decode().strip()

    def settimeout(self, timeout):
        assert timeout > 0

    def recv(self, size):
        output = self.outputs[self.command]
        if isinstance(output, BaseException):
            raise output
        return f"{self.command}\r\n{output}\r\n{self.prompt}".encode()

    def close(self):
        self.close_calls += 1


class SingleShellClient:
    """Model a target that refuses overlapping shells on the same SSH client."""
    def __init__(self, channels):
        self.channels = iter(channels)
        self.opened = []
        self.closed = False

    def invoke_shell(self, **kwargs):
        assert not self.closed, "parent session was closed"
        if any(not channel.close_calls for channel in self.opened):
            raise OSError("Resource shortage")
        channel = next(self.channels)
        self.opened.append(channel)
        return channel

    def close(self):
        self.closed = True


def session_for(channels):
    client = SingleShellClient(channels)
    return DeviceSession(client, client.close), client


def prompt_cli(session):
    return PromptCLI(session, paging_command="terminal length 0",
                     prompt_pattern=r"^(.+#)$", rejected=lambda x: "% Invalid" in x,
                     platform_name="test")


@pytest.mark.parametrize("factory", [prompt_cli, CiscoIOSCLI, CiscoXRCLI])
@pytest.mark.parametrize("failure", [None, "send", "prompt", "paging", "rejected", "command"])
def test_helper_cleanup_and_parent_ownership(factory, failure):
    outputs = {"": "", "terminal length 0": "", "show version": "version"}
    if failure in {"prompt", "paging", "command"}:
        command = {"prompt": "", "paging": "terminal length 0", "command": "show version"}[failure]
        outputs[command] = socket.timeout("read failed")
    if failure == "rejected":
        outputs["terminal length 0"] = "% Invalid input"
    channel = Channel("device#", outputs, send_failure=failure == "send")
    next_channel = Channel("device#", {})
    session, client = session_for([channel, next_channel])

    def collect():
        with closing(factory(session)) as cli:
            assert cli.run_command("show version") == "version"
        cli.close()  # Explicit repeated cleanup must be harmless.

    if failure:
        with pytest.raises((OSError, InteractiveCLIError, CiscoIOSCLIError)):
            collect()
    else:
        collect()
    assert channel.close_calls == 1
    assert not client.closed
    assert session.invoke_shell() is next_channel
    next_channel.close()
    session.close()
    assert client.closed


@pytest.mark.parametrize("device", DEVICES, ids=[d[2] for d in DEVICES])
def test_inventory_interfaces_vlans_share_one_session_without_retained_shells(tmp_path, device):
    version, platform, _, _, _ = device
    case = INTERFACES[platform]
    prompt = case["prompt"]
    identity = Channel(prompt, {
        "": "", "terminal length 0": "", "screen-length 0 temporary": "",
        "show version": version if platform != "huawei_vrp" else "% Invalid input",
        "display version": version, "show inventory": "", "show chassis": "", "display esn": "",
    })
    interface = Channel(prompt, {"": "", case["paging"]: "", case["command"]: case["output"]})
    vlan_prompt, paging, command, output = VLANS[platform]
    vlan = Channel(vlan_prompt, {"": "", paging: "", command: output})
    session, client = session_for([identity, interface, vlan])
    resolver = DeviceInventoryResolver(JsonInventoryStore(tmp_path / "inventory.json"))

    context = resolver.resolve(session, management_ip="192.0.2.1")
    assert identity.close_calls == 1
    assert InterfaceService().collect(session, context)
    assert interface.close_calls == 1
    assert VlanService().collect(session, context).platform == platform
    assert vlan.close_calls == 1
    assert client.opened == [identity, interface, vlan]
    assert not client.closed
    session.close()
    assert client.closed


@pytest.mark.parametrize("platform", INTERFACES)
@pytest.mark.parametrize("capability", ["interface", "vlan"])
@pytest.mark.parametrize("failure", ["read", "rejected", "parse"])
def test_capability_failure_releases_shell(platform, capability, failure, monkeypatch):
    if capability == "interface":
        case = INTERFACES[platform]
        prompt, paging, command, output = (case[k] for k in ["prompt", "paging", "command", "output"])
        service, error = InterfaceService(), InterfaceCapabilityError
        from orbitflow.capabilities.interfaces import _ADAPTERS
        parser = "parse_output" if platform.startswith("cisco") else None
    else:
        prompt, paging, command, output = VLANS[platform]
        service, error = VlanService(), VlanCapabilityError
        parser = None
    if failure == "read":
        output = socket.timeout("read failed")
    elif failure == "rejected":
        output = INTERFACES[platform]["rejection"]
    else:
        # Raise within parsing after a successful command, independent of parser grammar.
        def fail_parse(*args, **kwargs):
            raise ValueError("parse failed")
        if parser:
            monkeypatch.setattr(_ADAPTERS[platform], parser, staticmethod(fail_parse))
        else:
            vendor = "cisco" if platform.startswith("cisco") else "huawei" if platform == "huawei_vrp" else "ubiquiti"
            names = {
                ("huawei", "interface"): "parse_interface_description",
                ("ubiquiti", "interface"): "parse_interfaces_status",
                ("huawei", "vlan"): "parse_huawei_config",
                ("ubiquiti", "vlan"): "parse_edgeswitch_config",
                ("cisco", "vlan"): "parse_ios_xr_running_config" if platform == "cisco_xr" else "parse_ios_running_config",
            }
            monkeypatch.setattr(f"orbitflow.vendors.{vendor}.{capability}s.{names[vendor, capability]}", fail_parse)
    channel = Channel(prompt, {"": "", paging: "", command: output})
    session, client = session_for([channel])
    with pytest.raises(error):
        service.collect(session, device_ip="192.0.2.1", platform=platform)
    assert channel.close_calls == 1
    assert not client.closed


@pytest.mark.parametrize("failure", ["read", "unknown", "store"])
def test_inventory_failure_releases_shell(tmp_path, failure, monkeypatch):
    channel = Channel("sw#", {
        "": "", "terminal length 0": "", "screen-length 0 temporary": "",
        "show version": DEVICES[0][0], "show inventory": "", "display version": "unknown",
    })
    if failure == "read":
        channel.outputs["show version"] = socket.timeout("read failed")
    elif failure == "unknown":
        channel.outputs["show version"] = "unknown"
    store = JsonInventoryStore(tmp_path / "inventory.json")
    if failure == "store":
        def fail_store(context):
            raise OSError("store failed")
        monkeypatch.setattr(store, "reconcile", fail_store)
    session, client = session_for([channel])
    with pytest.raises(DeviceInventoryError):
        DeviceInventoryResolver(store).resolve(session, management_ip="192.0.2.1")
    assert channel.close_calls == 1
    assert not client.closed
