from datetime import datetime, timezone
from importlib.util import module_from_spec, spec_from_file_location
from io import StringIO
import json
from pathlib import Path

from openpyxl import Workbook

from orbitflow.models import DeviceContext
from orbitflow.transport import DeviceSession, TransportConfig

_SCRIPT = Path(__file__).parents[1] / "scripts" / "live_validate_inventory_batch.py"
_SPEC = spec_from_file_location("live_validate_inventory_batch", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
batch = module_from_spec(_SPEC)
_SPEC.loader.exec_module(batch)
NOW = datetime(2026, 9, 22, 14, 0, tzinfo=timezone.utc)


def _write_workbook(path, rows):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["management_ip", "username", "password", "future_column"])
    for row in rows:
        sheet.append(row)
    workbook.save(path)


def _context(management_ip):
    return DeviceContext(
        device_id=f"id-{management_ip}",
        management_ip=management_ip,
        observed_management_ips=(management_ip,),
        hostname="router",
        vendor="Cisco",
        platform="cisco_xr",
        device_family="NCS540",
        hardware_model="NCS-540",
        capability_profile="ncs540_l2",
        capability_flags=("l2_subinterface",),
        serial_number="FOC2643NCN3",
        software_version="7.7.2",
        uptime="1 year",
        last_successful_collection=NOW,
        last_collection_attempt=NOW,
    )


def test_load_targets_reads_multiple_rows_and_ignores_optional_columns(tmp_path):
    path = tmp_path / "devices.xlsx"
    _write_workbook(
        path,
        [
            ["192.0.2.1", "first-user", "first-password", "ignored"],
            ["192.0.2.2", "second-user", "second-password", "ignored-too"],
        ],
    )

    assert batch.load_targets(path) == [
        {
            "management_ip": "192.0.2.1",
            "username": "first-user",
            "password": "first-password",
        },
        {
            "management_ip": "192.0.2.2",
            "username": "second-user",
            "password": "second-password",
        },
    ]


def test_batch_uses_row_credentials_no_override_continues_and_excludes_secrets(
    tmp_path, monkeypatch
):
    targets = [
        {
            "management_ip": "192.0.2.1",
            "username": "user-one",
            "password": "secret-one",
        },
        {
            "management_ip": "192.0.2.2",
            "username": "user-two",
            "password": "secret-two",
        },
        {
            "management_ip": "192.0.2.3",
            "username": "user-three",
            "password": "secret-three",
        },
    ]
    connections = []
    resolutions = []
    session = DeviceSession(object(), lambda: None)

    class FakeStore:
        def __init__(self, path):
            self.path = path

    class FakeResolver:
        def __init__(self, store):
            self.store = store
            self.last_events = ("management_ip_changed",)

        def resolve(self, supplied_session, **kwargs):
            resolutions.append((supplied_session, kwargs))
            return _context(kwargs["management_ip"])

    def fake_connect(host, credentials, config):
        connections.append((host, credentials, config))
        if host == "192.0.2.2":
            raise RuntimeError("secret-two user-two must never escape")
        return session

    monkeypatch.setattr(batch, "JsonInventoryStore", FakeStore)
    monkeypatch.setattr(batch, "DeviceInventoryResolver", FakeResolver)
    monkeypatch.setattr(batch, "connect_device", fake_connect)
    results_path = tmp_path / "results.json"
    output = StringIO()
    config = TransportConfig("proxy", "cluster", "bastion", "teleport-user")

    payload = batch.run_batch_validation(
        targets,
        config,
        inventory_path=tmp_path / "inventory.json",
        results_path=results_path,
        output=output,
        clock=lambda: NOW,
    )

    assert [
        (host, creds.username, creds.password) for host, creds, _ in connections
    ] == [
        ("192.0.2.1", "user-one", "secret-one"),
        ("192.0.2.2", "user-two", "secret-two"),
        ("192.0.2.3", "user-three", "secret-three"),
    ]
    assert [call[1] for call in resolutions] == [
        {"management_ip": "192.0.2.1"},
        {"management_ip": "192.0.2.3"},
    ]
    assert all("platform_override" not in call[1] for call in resolutions)
    assert payload["collection_time"] == NOW.isoformat()
    assert (payload["total_devices"], payload["successful"], payload["failed"]) == (
        3,
        2,
        1,
    )
    assert [item["success"] for item in payload["results"]] == [True, False, True]
    assert payload["results"][1] == {
        "management_ip": "192.0.2.2",
        "success": False,
        "device_context": None,
        "reconciliation_events": [],
        "error": "inventory validation failed (RuntimeError)",
    }
    rendered = results_path.read_text() + output.getvalue()
    for secret in (
        "user-one",
        "user-two",
        "user-three",
        "secret-one",
        "secret-two",
        "secret-three",
    ):
        assert secret not in rendered
    assert json.loads(results_path.read_text()) == payload
    successful_context = payload["results"][0]["device_context"]
    assert successful_context["observed_management_ips"] == ["192.0.2.1"]
    assert successful_context["capability_flags"] == ["l2_subinterface"]
    assert successful_context["collection_status"] == "success"
    assert successful_context["collection_error"] == ""
