"""Offline plan/approval contract regression tests; all identities are synthetic."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import socket
import sqlite3

import pytest

from orbitflow.configuration import ApprovalStore, ChangePlan, PlanError, create_plan, load_plan, save_plan
from orbitflow.configuration.cli import main
from orbitflow.configuration.plans import POLICY, canonical
from orbitflow.inventory.store import JsonInventoryStore
from orbitflow.models import DeviceContext


NOW = datetime(2026, 10, 8, tzinfo=timezone.utc)


@pytest.fixture
def context():
    return DeviceContext("switch-1", "192.0.2.1", ("192.0.2.1",), "switch-1", "Cisco", "cisco_xe",
                         "C3850", "WS-C3850", "c3850_switching", ("classic_switchport",), "EXAMPLE1",
                         "16.12", "", NOW, NOW)


@pytest.fixture
def request_data():
    return dict(schema_version=1, change_id="CHG-75", source=dict(kind="template", reference="vlan-create", version="1"),
                intent="Create customer VLAN", execution_policy=dict(POLICY),
                targets=[dict(inventory_id="switch-1", expected_hostname="switch-1", expected_platform="cisco_xe",
                              operations=[dict(kind="ensure_vlan_present", vlan_id=3500, vlan_name="CUSTOMER",
                                               precondition=dict(present=False, name=""),
                                               verification=dict(present=True, name="CUSTOMER"))])])


def test_roundtrip_immutable_and_deterministic(tmp_path, context, request_data):
    plan = create_plan(request_data, [context])
    other = create_plan(dict(reversed(list(request_data.items()))), [context])
    assert plan.digest == other.digest
    request_data["intent"] = "Changed"
    copied = plan.to_dict()
    copied["intent"] = "Changed"
    assert plan.digest == other.digest
    with pytest.raises(AttributeError):
        plan.content = "changed"
    save_plan(plan, tmp_path / "plan.json")
    assert load_plan(tmp_path / "plan.json") == plan
    with pytest.raises(FileExistsError):
        save_plan(plan, tmp_path / "plan.json")
    assert "configure terminal" in plan.preview()


@pytest.mark.parametrize("kind", ["manual", "spreadsheet", "template", "compliance"])
def test_sources(context, request_data, kind):
    request_data["source"]["kind"] = kind
    if kind == "manual":
        request_data["targets"][0]["operations"][0]["commands"] = ["configure terminal", "vlan 3500", "name CUSTOMER", "end"]
    assert create_plan(request_data, [context]).to_dict()["source"]["kind"] == kind


@pytest.mark.parametrize("mutation", [
    lambda r: r.update(schema_version=2),
    lambda r: r.update(schema_version=True),
    lambda r: r.update(password="EXAMPLE-CREDENTIAL"),
    lambda r: r.update(intent="password=EXAMPLE-CREDENTIAL"),
    lambda r: r["source"].update(reference="token EXAMPLE-CREDENTIAL"),
    lambda r: r["targets"].append(deepcopy(r["targets"][0])),
    lambda r: r["targets"][0].update(expected_hostname="wrong"),
    lambda r: r["targets"][0].update(expected_platform="cisco_ios"),
    lambda r: r["execution_policy"].update(require_approval=False),
    lambda r: r["execution_policy"].update(dry_run=False),
    lambda r: r["execution_policy"].update(max_devices_per_run=True),
    lambda r: r["targets"][0]["operations"].append(deepcopy(r["targets"][0]["operations"][0])),
])
def test_invalid_requests(context, request_data, mutation):
    mutation(request_data)
    with pytest.raises(PlanError) as error:
        create_plan(request_data, [context])
    assert "EXAMPLE-CREDENTIAL" not in str(error.value)


@pytest.mark.parametrize("changes", [
    dict(vlan_id=1), dict(vlan_id=1002), dict(vlan_id=True), dict(vlan_id=4095),
    dict(kind="delete_vlan"), dict(vlan_name="customer\nreload"), dict(vlan_name="password"),
    dict(precondition={}), dict(precondition=dict(present=True, name="OTHER")),
    dict(verification={}), dict(verification=dict(present=False, name="CUSTOMER")),
    dict(commands=["reload"]), dict(commands=["username example secret EXAMPLE-CREDENTIAL"]),
])
def test_invalid_operations(context, request_data, changes):
    request_data["targets"][0]["operations"][0].update(changes)
    with pytest.raises(PlanError) as error:
        create_plan(request_data, [context])
    assert "EXAMPLE-CREDENTIAL" not in str(error.value)


def test_identity_and_profiles(context, request_data):
    for contexts in ([], [context, context], [replace(context, collection_status="failed")],
                     [context, replace(context, device_id="other")],
                     [replace(context, capability_profile="unknown")],
                     [replace(context, device_family="ASR920")]):
        with pytest.raises(PlanError):
            create_plan(request_data, contexts)
    ios = replace(context, platform="cisco_ios", device_family="C3750X", capability_profile="c3750x_switching")
    request_data["targets"][0]["expected_platform"] = "cisco_ios"
    assert create_plan(request_data, [ios])


def test_noop(context, request_data):
    request_data["targets"][0]["operations"][0]["precondition"] = dict(present=True, name="CUSTOMER")
    assert create_plan(request_data, [context]).to_dict()["targets"][0]["operations"][0]["commands"] == []


def test_approval_lifecycle(tmp_path, context, request_data):
    plan = create_plan(request_data, [context])
    store = ApprovalStore(tmp_path)
    with pytest.raises(PlanError):
        store.verify(plan, now=NOW)
    expiry = NOW + timedelta(hours=1)
    record = store.decide(plan, "approved", "operator", now=NOW, expires_at=expiry)
    assert ApprovalStore(tmp_path).verify(plan, now=NOW)["digest"] == plan.digest
    record["status"] = "rejected"
    assert store.verify(plan, now=NOW)["status"] == "approved"
    for when in (expiry, NOW - timedelta(seconds=1)):
        with pytest.raises(PlanError):
            store.verify(plan, now=when)
    for state in ("rejected", "expired"):
        store.decide(plan, state, "operator", now=NOW)
        with pytest.raises(PlanError):
            store.verify(plan, now=NOW)
    with pytest.raises(PlanError):
        store.decide(plan, "approved", "operator", now=NOW, expires_at=NOW)
    with pytest.raises(PlanError):
        store.decide(plan, "approved", "operator", now=NOW.replace(tzinfo=None), expires_at=expiry)


@pytest.mark.parametrize("field", ["intent", "target", "commands", "policy", "precondition", "source"])
def test_changes_invalidate_approval(tmp_path, context, request_data, field):
    plan = create_plan(request_data, [context])
    store = ApprovalStore(tmp_path)
    store.decide(plan, "approved", "operator", now=NOW, expires_at=NOW + timedelta(hours=1))
    if field == "intent":
        request_data["intent"] = "Different intent"
    elif field == "target":
        context = replace(context, management_ip="192.0.2.2")
    elif field == "commands":
        op = request_data["targets"][0]["operations"][0]
        op["vlan_name"] = op["verification"]["name"] = "OTHER"
    elif field == "policy":
        request_data["execution_policy"]["max_devices_per_run"] = 4
    elif field == "source":
        request_data["source"]["version"] = "2"
    else:
        request_data["targets"][0]["operations"][0]["precondition"] = dict(present=True, name="CUSTOMER")
    changed = create_plan(request_data, [context])
    assert changed.digest != plan.digest
    with pytest.raises(PlanError):
        store.verify(changed, now=NOW)


def test_tampered_artifacts(tmp_path, context, request_data):
    plan = create_plan(request_data, [context])
    path = tmp_path / "plan.json"
    save_plan(plan, path)
    content = json.loads(path.read_text())
    content["plan"]["intent"] = "Changed"
    path.write_text(json.dumps(content))
    with pytest.raises(PlanError):
        load_plan(path)
    with pytest.raises(PlanError):
        ChangePlan('{"schema_version":1,"schema_version":1}')
    store = ApprovalStore(tmp_path / "authority")
    store.decide(plan, "approved", "operator", now=NOW, expires_at=NOW + timedelta(hours=1))
    with sqlite3.connect(store.root / "approvals.sqlite3") as db:
        db.execute("UPDATE decisions SET body = replace(body, 'operator', 'attacker')")
    with pytest.raises(PlanError):
        store.verify(plan, now=NOW)


def test_end_to_end_cli_without_network(tmp_path, context, request_data, monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail("offline workflow attempted network access")
    monkeypatch.setattr(socket, "socket", forbidden)
    inventory = tmp_path / "inventory.json"
    JsonInventoryStore(inventory, id_factory=lambda: "switch-1").reconcile(context)
    request = tmp_path / "request.json"
    request.write_text(canonical(request_data))
    path = tmp_path / "plan.json"
    authority = str(tmp_path / "authority")
    assert main(["create", str(request), "--inventory", str(inventory), "--output", str(path)]) == 0
    assert main(["validate", str(path)]) == 0
    assert main(["preview", str(path)]) == 0
    digest = load_plan(path).digest
    assert main(["approve", str(path), "--authority", authority, "--actor", "operator", "--digest", digest,
                 "--expires-at", "2099-01-01T00:00:00+00:00"]) == 0
    assert main(["verify-approval", str(path), "--authority", authority]) == 0
    assert main(["reject", str(path), "--authority", authority, "--actor", "operator"]) == 0
    assert main(["verify-approval", str(path), "--authority", authority]) == 2
    assert "Approval verified" in capsys.readouterr().out


def test_cli_redaction(tmp_path, capsys):
    path = tmp_path / "invalid.json"
    path.write_text('{"password":"EXAMPLE-CREDENTIAL"}')
    assert main(["validate", str(path)]) == 2
    assert "EXAMPLE-CREDENTIAL" not in capsys.readouterr().out


def test_approval_secret_rejection_and_missing_key(tmp_path, context, request_data):
    plan = create_plan(request_data, [context])
    store = ApprovalStore(tmp_path / "authority")
    with pytest.raises(PlanError):
        store.decide(plan, "approved", "password=EXAMPLE-CREDENTIAL", now=NOW,
                     expires_at=NOW + timedelta(hours=1))
    assert not store.root.exists()
    store.decide(plan, "approved", "operator", now=NOW, expires_at=NOW + timedelta(hours=1))
    (store.root / "approval.key").unlink()
    with pytest.raises(PlanError):
        store.verify(plan, now=NOW)
    with pytest.raises(PlanError):
        store.decide(plan, "approved", "operator", now=NOW, expires_at=NOW + timedelta(hours=1))


def test_missing_checks_manual_commands_and_ipv6(context, request_data):
    del request_data["targets"][0]["operations"][0]["verification"]
    with pytest.raises(PlanError):
        create_plan(request_data, [context])
    request_data["targets"][0]["operations"][0]["verification"] = dict(present=True, name="CUSTOMER")
    request_data["source"]["kind"] = "manual"
    with pytest.raises(PlanError):
        create_plan(request_data, [context])
    request_data["source"]["kind"] = "spreadsheet"
    plan = create_plan(request_data, [replace(context, management_ip="::1")])
    assert plan.to_dict()["targets"][0]["identity"]["management_ip"] == "::1"
