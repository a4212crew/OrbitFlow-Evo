from datetime import datetime, timezone
from importlib.util import module_from_spec, spec_from_file_location
from io import StringIO
from pathlib import Path

from orbitflow.models import InterfaceVlanObservation, VlanObject, VlanState
from orbitflow.transport import DeviceCredentials, DeviceSession, TransportConfig

_SCRIPT = Path(__file__).parents[1] / "scripts" / "live_validate_vlans.py"
_SPEC = spec_from_file_location("live_validate_vlans", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
live_validate_vlans = module_from_spec(_SPEC)
_SPEC.loader.exec_module(live_validate_vlans)


def test_value_formatter_distinguishes_none_from_explicitly_empty_tuple():
    assert live_validate_vlans._format_value(None) == "-"
    assert live_validate_vlans._format_value(()) == "[]"


def test_live_validation_reuses_transport_and_vlan_service(monkeypatch):
    session = DeviceSession(object(), lambda: None)
    credentials = DeviceCredentials(username="operator", password="secret-value")
    config = TransportConfig("proxy:443", "cluster", "bastion", "teleport-user")
    state = VlanState(
        "edge-01",
        "192.0.2.10",
        "cisco_xe",
        (
            InterfaceVlanObservation(
                interface_name="Gi0/0/0",
                description="Customer",
                mode="trunk",
                allowed_vlans=(100, 200),
                referenced_vlans=(100, 200),
            ),
        ),
        (VlanObject("vlan", "100", "CUSTOMER", (100,)),),
        datetime(2026, 9, 21, tzinfo=timezone.utc),
    )
    calls = []
    context = object()

    class FakeResolver:
        def __init__(self, store):
            pass

        def resolve(self, supplied_session, **target):
            calls.append(("resolve", supplied_session, target))
            return context

    monkeypatch.setattr(live_validate_vlans, "DeviceInventoryResolver", FakeResolver)

    def fake_connect(host, supplied_credentials, supplied_config):
        calls.append(("connect", host, supplied_credentials, supplied_config))
        return session

    class FakeVlanService:
        def collect(self, supplied_session, **device):
            calls.append(("collect", supplied_session, device))
            return state

    monkeypatch.setattr(live_validate_vlans, "connect_device", fake_connect)
    monkeypatch.setattr(live_validate_vlans, "VlanService", FakeVlanService)
    output = StringIO()

    result = live_validate_vlans.run_live_validation(
        "192.0.2.10", "cisco_xe", credentials, config, output=output
    )

    assert result is state
    assert calls == [
        ("connect", "192.0.2.10", credentials, config),
        ("resolve", session, {"management_ip": "192.0.2.10", "platform_override": "cisco_xe"}),
        ("collect", session, {"context": context}),
    ]
    rendered = output.getvalue()
    assert "Device: edge-01" in rendered
    assert "type=vlan, id=100, name=CUSTOMER, vlan_ids=100" in rendered
    assert "Gi0/0/0: description=Customer, mode=trunk" in rendered
    assert "allowed_vlans=100,200" in rendered
    assert "secret-value" not in rendered


def test_main_prompts_only_for_password_and_uses_configured_target(monkeypatch):
    calls = []

    def fake_getpass(prompt):
        calls.append(("getpass", prompt))
        return "not-rendered"

    def fail_input(*_args, **_kwargs):
        raise AssertionError("main must not prompt for non-secret target settings")

    def fake_run(host, platform, credentials, config):
        calls.append(("run", host, platform, credentials, config))

    monkeypatch.setattr(live_validate_vlans.getpass, "getpass", fake_getpass)
    monkeypatch.setattr("builtins.input", fail_input)
    monkeypatch.setattr(
        live_validate_vlans, "_linux_teleport_identity_paths", lambda: (None, None)
    )
    monkeypatch.setattr(live_validate_vlans, "run_live_validation", fake_run)

    live_validate_vlans.main()

    assert calls[0] == ("getpass", "Device password: ")
    _, host, platform, credentials, config = calls[1]
    assert (host, platform) == ("10.251.10.98", "cisco_xr")
    assert credentials == DeviceCredentials("lightningadmin", "not-rendered")
    assert config == TransportConfig(
        "teleport.lynhamnetworks.au:443",
        "lynhamcluster",
        "bastion-lyn-dc1-vic",
        "lightningadmin",
    )
