from datetime import datetime, timezone
from importlib.util import module_from_spec, spec_from_file_location
from io import StringIO
from pathlib import Path

from orbitflow.models import DeviceContext
from orbitflow.transport import DeviceCredentials, DeviceSession, TransportConfig

_SCRIPT = Path(__file__).parents[1] / "scripts" / "live_validate_inventory.py"
_SPEC = spec_from_file_location("live_validate_inventory", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
live_validate_inventory = module_from_spec(_SPEC)
_SPEC.loader.exec_module(live_validate_inventory)


def _context() -> DeviceContext:
    collected = datetime(2026, 9, 22, 12, 30, tzinfo=timezone.utc)
    return DeviceContext(
        device_id="device-123",
        management_ip="192.0.2.10",
        observed_management_ips=("192.0.2.9", "192.0.2.10"),
        hostname="edge-01",
        vendor="Cisco",
        platform="cisco_xe",
        device_family="ASR920",
        hardware_model="ASR-920-24SZ-M",
        capability_profile="cisco_asr920",
        capability_flags=("evc", "switchport"),
        serial_number="SERIAL123",
        software_version="17.6.7",
        uptime="2 weeks, 1 day",
        last_successful_collection=collected,
        last_collection_attempt=collected,
    )


def test_live_validation_delegates_to_transport_resolver_and_store(monkeypatch):
    session = DeviceSession(object(), lambda: None)
    credentials = DeviceCredentials("operator", "top-secret-password")
    config = TransportConfig("proxy:443", "cluster", "bastion", "teleport-user")
    context = _context()
    calls = []

    class FakeStore:
        def __init__(self, path):
            calls.append(("store", path))

        def contexts(self):
            calls.append(("contexts",))
            return ()

    class FakeResolver:
        def __init__(self, store):
            calls.append(("resolver", store))
            self.last_events = ("management_ip_changed",)

        def resolve(self, supplied_session, **kwargs):
            calls.append(("resolve", supplied_session, kwargs))
            return context

    def fake_connect(host, supplied_credentials, supplied_config):
        calls.append(("connect", host, supplied_credentials, supplied_config))
        return session

    monkeypatch.setattr(live_validate_inventory, "JsonInventoryStore", FakeStore)
    monkeypatch.setattr(
        live_validate_inventory, "DeviceInventoryResolver", FakeResolver
    )
    monkeypatch.setattr(live_validate_inventory, "connect_device", fake_connect)
    output = StringIO()

    result = live_validate_inventory.run_live_validation(
        "192.0.2.10",
        credentials,
        config,
        inventory_path=Path("validation/inventory.json"),
        output=output,
    )

    assert result is context
    assert calls[0] == ("store", Path("validation/inventory.json"))
    assert calls[1][0] == "resolver"
    assert calls[2] == ("contexts",)
    assert calls[3] == ("connect", "192.0.2.10", credentials, config)
    assert calls[4] == (
        "resolve",
        session,
        {"management_ip": "192.0.2.10"},
    )
    assert calls[5] == ("contexts",)
    assert "platform_override" not in calls[4][2]
    assert "snapshot_path: validation/inventory.json\n" in output.getvalue()


def test_context_output_includes_all_normalized_fields_and_events():
    output = StringIO()

    live_validate_inventory._print_context(
        _context(), ("management_ip_changed", "hostname_collision"), output=output
    )

    rendered = output.getvalue()
    expected = {
        "device_id": "device-123",
        "management_ip": "192.0.2.10",
        "observed_management_ips": "192.0.2.9, 192.0.2.10",
        "hostname": "edge-01",
        "vendor": "Cisco",
        "platform": "cisco_xe",
        "device_family": "ASR920",
        "hardware_model": "ASR-920-24SZ-M",
        "capability_profile": "cisco_asr920",
        "capability_flags": "evc, switchport",
        "serial_number": "SERIAL123",
        "software_version": "17.6.7",
        "uptime": "2 weeks, 1 day",
        "collection_status": "success",
        "last_successful_collection": "2026-09-22T12:30:00+00:00",
        "last_collection_attempt": "2026-09-22T12:30:00+00:00",
        "collection_error": "-",
        "reconciliation_events": "management_ip_changed, hostname_collision",
    }
    for name, value in expected.items():
        assert f"{name}: {value}\n" in rendered


def test_rendered_context_does_not_leak_credentials(monkeypatch):
    credentials = DeviceCredentials(
        username="credential-user",
        password="top-secret-password",
        pkey="private-key-value",
    )
    session = DeviceSession(object(), lambda: None)

    class FakeStore:
        def __init__(self, _path):
            pass

        def contexts(self):
            return ()

    class FakeResolver:
        def __init__(self, _store):
            self.last_events = ()

        def resolve(self, _session, **_kwargs):
            return _context()

    monkeypatch.setattr(
        live_validate_inventory, "DeviceInventoryResolver", FakeResolver
    )
    monkeypatch.setattr(live_validate_inventory, "JsonInventoryStore", FakeStore)
    monkeypatch.setattr(
        live_validate_inventory, "connect_device", lambda *_args: session
    )
    output = StringIO()

    live_validate_inventory.run_live_validation(
        "192.0.2.10",
        credentials,
        TransportConfig("proxy", "cluster", "bastion", "teleport-user"),
        output=output,
    )

    rendered = output.getvalue()
    assert "credential-user" not in rendered
    assert "top-secret-password" not in rendered
    assert "private-key-value" not in rendered
    assert "reconciliation_events: []" in rendered


def test_inventory_state_output_is_explicit_for_before_after_comparison():
    output = StringIO()

    live_validate_inventory._print_inventory_state("Before", (), output=output)
    live_validate_inventory._print_inventory_state(
        "After", (_context(),), output=output
    )

    rendered = output.getvalue()
    assert (
        "Before inventory state:\ntotal_stored_device_count: 0\ndevices: []\n"
        in rendered
    )
    assert "After inventory state:\ntotal_stored_device_count: 1\n" in rendered
    assert "  device_id: device-123\n" in rendered
    assert "  serial_number: SERIAL123\n" in rendered
    assert "  management_ip: 192.0.2.10\n" in rendered
    assert "  observed_management_ips: 192.0.2.9, 192.0.2.10\n" in rendered


def test_main_prompts_only_for_password_and_uses_no_platform(monkeypatch):
    calls = []

    monkeypatch.setattr(
        live_validate_inventory.getpass,
        "getpass",
        lambda prompt: calls.append(("getpass", prompt)) or "not-rendered",
    )
    monkeypatch.setattr(
        "builtins.input",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("main must not prompt for non-secret settings")
        ),
    )
    monkeypatch.setattr(
        live_validate_inventory, "_linux_teleport_identity_paths", lambda: (None, None)
    )
    monkeypatch.setattr(
        live_validate_inventory,
        "run_live_validation",
        lambda *args, **kwargs: calls.append(("run", args, kwargs)),
    )

    live_validate_inventory.main()

    assert calls[0] == ("getpass", "Device password: ")
    _, args, kwargs = calls[1]
    assert args[0] == live_validate_inventory.DEVICE_HOST
    assert args[1] == DeviceCredentials("lightningadmin", "not-rendered")
    assert isinstance(args[2], TransportConfig)
    assert kwargs == {}
