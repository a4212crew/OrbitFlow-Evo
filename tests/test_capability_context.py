"""Resolved identity feeds existing adapters without rediscovery or reconnects."""
from dataclasses import replace
from io import StringIO

import pytest

from orbitflow.capabilities import (
    InterfaceService, VlanService, InterfaceCapabilityError, VlanCapabilityError,
)
from orbitflow.inventory import DeviceInventoryResolver, JsonInventoryStore
from orbitflow.transport import DeviceSession, DeviceCredentials, TransportConfig
from test_device_inventory import Runner
from test_interface_capability import CASES as INTERFACES, make_session
from test_vlan_capability import CASES as VLANS, session_for


DEVICES = [
    ("Cisco IOS Software, Version 15.2\nsw uptime is 1 day\nWS-C3750X", "cisco_ios", "C3750X", "c3750x_switching", "sw#"),
    ("Cisco IOS Software, Version 15.3\nsw uptime is 1 day\nME-3600X", "cisco_ios", "ME3600X", "me3600x_evc", "sw#"),
    ("Cisco IOS XE Software, Version 17.6\nsw uptime is 1 day\nASR920", "cisco_xe", "ASR920", "asr920_evc", "sw#"),
    ("Cisco IOS XR Software, Version 7.7\nsw uptime is 1 day\nNCS-540", "cisco_xr", "NCS540", "ncs540_l2", "sw#"),
    ("Huawei VRP software Version 5.1\nNE05E uptime is 1 day", "huawei_vrp", "NE05E", "ne05e", "<sw>"),
    ("Ubiquiti EdgeSwitch\nModel: ES-48", "ubiquiti_edgeswitch", "EdgeSwitch", "edgeswitch", "(sw) #"),
]
EVC = "interface GigabitEthernet0/1\n service instance 100 ethernet\n  encapsulation dot1q 445\n  bridge-domain 900\n !\n!"


def resolve(tmp_path, session, device):
    version, platform, family, profile, prompt = device
    runner = Runner({"show version": version if platform != "huawei_vrp" else "",
                     "display version": version, "show inventory": "", "show chassis": "", "display esn": ""}, prompt)
    def factory(supplied):
        assert supplied is session
        return runner
    context = DeviceInventoryResolver(JsonInventoryStore(tmp_path / "inventory.json"), runner_factory=factory).resolve(session, management_ip="192.0.2.10")
    assert (context.platform, context.device_family, context.capability_profile) == (platform, family, profile)
    return context


@pytest.mark.parametrize("device", DEVICES, ids=[d[2] for d in DEVICES])
def test_resolved_context_collects_both_capabilities(tmp_path, device):
    platform = device[1]
    case = INTERFACES[platform]
    prompt, paging, command = case['prompt'], case['paging'], case['command']
    session, channel = make_session([prompt.encode(), f"{paging}\r\n{prompt}".encode(), f"{command}\r\n{case['output']}\r\n{prompt}".encode()])
    prompt_v, paging_v, command_v, output_v = VLANS[platform]
    if platform in {"cisco_ios", "cisco_xe"}:
        output_v += "\n" + EVC
    vlan_session, vlan_channel = session_for(prompt_v, paging_v, command_v, output_v)
    channels = iter([channel, vlan_channel])
    class Client:
        def invoke_shell(self, **kwargs):
            return next(channels)
    session = DeviceSession(Client(), lambda: None)
    context = resolve(tmp_path, session, device)
    records = InterfaceService().collect(session, context)
    assert records
    assert all((r.device_ip, r.device_name, r.platform) == (context.management_ip, context.hostname, platform) for r in records)
    assert channel.sent == [b"\n", f"{paging}\n".encode(), f"{command}\n".encode()]

    # Both capability adapters open their shells on the same established session.
    state = VlanService().collect(session, context=context)
    assert (state.device_ip, state.device_name, state.platform) == (context.management_ip, context.hostname, platform)
    services = [i for i in state.interfaces if i.service_binding_name == "900"]
    assert bool(services) == (device[2] in {"ME3600X", "ASR920"})
    if services:
        assert services[0].referenced_vlans == (445,)
    assert vlan_channel.sent == [b"\n", f"{paging_v}\n".encode(), f"{command_v}\n".encode()]


@pytest.mark.parametrize("selection", ["profile", "family", "flags"])
def test_ios_evc_selection_uses_context_evidence(tmp_path, selection):
    session, _ = session_for("sw#", "terminal length 0", "show running-config", EVC)
    context = resolve(tmp_path, session, DEVICES[1])
    context = replace(context, device_family="ME3600X" if selection == "family" else "unknown",
                      capability_profile="me3600x_evc" if selection == "profile" else "unknown",
                      capability_flags=("evc",) if selection == "flags" else ())
    state = VlanService().collect(session, context)
    assert state.platform == "cisco_ios"
    assert state.interfaces[0].service_binding_name == "900"


@pytest.mark.parametrize("service,error", [(InterfaceService, InterfaceCapabilityError), (VlanService, VlanCapabilityError)])
def test_context_rejects_mixed_identity_before_using_session(tmp_path, service, error):
    context = resolve(tmp_path, object(), DEVICES[0])
    with pytest.raises(error, match="context cannot be combined"):
        service().collect(None, context, platform="cisco_xe")
    with pytest.raises(error, match="provide context"):
        service().collect(None)
    with pytest.raises(error, match="unsupported"):
        service().collect(None, replace(context, platform="unknown"))


@pytest.mark.parametrize("module_name", ["interfaces", "vlans"])
def test_validation_resolution_failure_closes_session_without_collecting(monkeypatch, tmp_path, module_name):
    from test_live_validate_interfaces import live_validate_interfaces
    from test_live_validate_vlans import live_validate_vlans
    module = live_validate_interfaces if module_name == "interfaces" else live_validate_vlans
    closed = []
    session = DeviceSession(object(), lambda: closed.append(True))
    monkeypatch.setattr(module, "connect_device", lambda *args: session)
    class Resolver:
        def __init__(self, store):
            pass
        def resolve(self, supplied, **kwargs):
            assert supplied is session
            assert kwargs['platform_override'] is None
            raise ValueError("unresolved")
    monkeypatch.setattr(module, "DeviceInventoryResolver", Resolver)
    with pytest.raises(ValueError, match="unresolved"):
        module.run_live_validation("192.0.2.10", None, DeviceCredentials("operator", "test"),
                                   TransportConfig("proxy", "cluster", "host", "user"),
                                   inventory_path=tmp_path / "inventory.json", output=StringIO())
    assert closed == [True]
