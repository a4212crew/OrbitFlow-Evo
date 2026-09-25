from datetime import datetime, timezone
from importlib.util import module_from_spec, spec_from_file_location
from io import StringIO
from pathlib import Path

from orbitflow.models import InterfaceRecord
from orbitflow.transport import DeviceCredentials, DeviceSession, TransportConfig

_SCRIPT = Path(__file__).parents[1] / "scripts" / "live_validate_interfaces.py"
_SPEC = spec_from_file_location("live_validate_interfaces", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
live_validate_interfaces = module_from_spec(_SPEC)
_SPEC.loader.exec_module(live_validate_interfaces)


def test_live_validation_reuses_transport_and_interface_service(monkeypatch):
    session = DeviceSession(object(), lambda: None)
    credentials = DeviceCredentials(username="operator", password="secret-value")
    config = TransportConfig(
        proxy="teleport.example:443",
        cluster="example",
        bastion_host="bastion",
        bastion_user="teleport-user",
    )
    records = [
        InterfaceRecord(
            device_name="edge-01",
            device_ip="192.0.2.10",
            platform="cisco_xe",
            port_name="Gi0/0/0",
            port_description="Customer uplink",
            admin_status="up",
            oper_status="down",
            collection_time=datetime(2026, 9, 20, tzinfo=timezone.utc),
        )
    ]
    calls = []
    from types import SimpleNamespace
    context = SimpleNamespace(management_ip="192.0.2.10", platform="cisco_xe")

    class FakeResolver:
        def __init__(self, store):
            pass

        def resolve(self, supplied_session, **target):
            calls.append(("resolve", supplied_session, target))
            return context

    monkeypatch.setattr(live_validate_interfaces, "DeviceInventoryResolver", FakeResolver)

    def fake_connect(host, supplied_credentials, supplied_config):
        calls.append(("connect", host, supplied_credentials, supplied_config))
        return session

    class FakeInterfaceService:
        def collect(self, supplied_session, **device):
            calls.append(("collect", supplied_session, device))
            return records

    monkeypatch.setattr(live_validate_interfaces, "connect_device", fake_connect)
    monkeypatch.setattr(
        live_validate_interfaces, "InterfaceService", FakeInterfaceService
    )
    output = StringIO()

    result = live_validate_interfaces.run_live_validation(
        "192.0.2.10",
        "cisco_xe",
        credentials,
        config,
        output=output,
    )

    assert result is records
    assert calls == [
        ("connect", "192.0.2.10", credentials, config),
        ("resolve", session, {"management_ip": "192.0.2.10", "platform_override": "cisco_xe"}),
        ("collect", session, {"context": context}),
    ]
    assert output.getvalue() == (
        "edge-01 (192.0.2.10, cisco_xe): 1 interface(s)\n"
        "  Gi0/0/0: admin=up, oper=down, description=Customer uplink\n"
    )
    assert "secret-value" not in output.getvalue()
