"""Synthetic, deterministic contracts; no live equipment or credentials."""
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
import socket

import pytest
from openpyxl import load_workbook

from orbitflow.configuration.plans import PlanError, canonical
from orbitflow.configuration.v2.catalogue import CATALOGUE, FAMILIES
from orbitflow.configuration.v2.planning import request, plan, review, BulkPlan, save, load
from orbitflow.configuration.v2.workbook import create_input, read_input, export_review, import_review, EXTRA
from orbitflow.configuration.v2.approvals import ReviewStore
from orbitflow.configuration.v2.observation import snapshot
from orbitflow.models import DeviceContext, InterfaceRecord, VlanObject, VlanState, ConfigFact
from orbitflow.compliance.vlan import safe_data

NOW = datetime(2026, 10, 11, tzinfo=timezone.utc)
IP = "192.0.2.10"


def template(family, function):
    return next(t for t in CATALOGUE if (t.family, t.function) == (family, function))


def inputs(t):
    p = {"management_ip": IP}
    examples = {
        "VLAN Database": dict(vlan_id=4002, name="Customer"),
        "Access Port": dict(interface="Gi1/0/1", vlan_id=4002),
        "Trunk Port": dict(interface="Gi1/0/1", action="Add", vlans=[4002]),
        "Interface Description": dict(interface="Gi1/0/1", description="Customer Site Alpha"),
        "EVC": dict(interface="Gi1/0/1", service_instance=10, encapsulation="dot1q", outer_vlan=4002, bridge_domain=4002, pop_tags=1),
        "L2VPN": dict(interface="Gi1/0/1", subinterface=10, encapsulation="dot1q", outer_vlan=4002, bridge_group="CUSTOMER", bridge_domain="BLUE"),
        "VLAN Port": dict(interface="0/1", action="Remove", mode="Tagged", vlans=[4002]),
        "Subinterface VSI": dict(interface="Gi1/0/1", subinterface=10, vlan_id=4002, encapsulation="vlan-type dot1q", vsi="BLUE"),
        "Manual CLI": dict(platform="cisco_ios", mode="interface", scope="Gi1/0/1", commands=" description Customer Site\n exit\n"),
    }
    return {**p, **examples[t.function]}


def observed(t, *, objects=None):
    platform, profile = FAMILIES[t.family]
    family = "C3850" if t.family == "C3850X" else t.family
    context = DeviceContext("device-1", IP, (IP,), "example", "Example", platform, family, family,
                            profile, (), "EXAMPLE", "1", "", NOW, NOW)
    name = inputs(t).get("interface", "Gi1/0/1")
    interface = InterfaceRecord("example", IP, platform, name, "Before", "up", "up", NOW)
    facts = (ConfigFact("interface", name, "running-config", 1, f"interface {name}"),)
    state = VlanState("example", IP, platform, (), tuple(objects or ()), NOW, facts)
    return snapshot(context, (interface,), state)


@pytest.mark.parametrize("t", CATALOGUE, ids=lambda t: t.id)
def test_all_22_schema_and_representative_cli(t):
    assert len(CATALOGUE) == 22
    p = inputs(t)
    r = request(t.id, p)
    result = plan([r], {} if t.family == "All" else {IP: observed(t)}, now=NOW).to_dict()["results"][0]
    cmds = result["commands"]
    assert not result["execution_authorized"]
    if t.family == "All":
        assert cmds == p["commands"]
        assert result["live_validation"] == "not_live_validated"
    elif t.function == "VLAN Database":
        expected = (["system-view", "vlan 4002", "description Customer", "quit", "quit"] if t.family == "NE05E" else
                    ["vlan database", "vlan 4002", 'vlan name 4002 "Customer"', "exit"] if t.family == "EdgeSwitch" else
                    ["configure terminal", "vlan 4002", "name Customer", "end"])
        assert cmds == expected
    elif t.function == "Interface Description":
        expected = (["system-view", "interface Gi1/0/1", "description Customer Site Alpha", "quit", "quit"] if t.family == "NE05E" else
                    ["configure", "interface Gi1/0/1", 'description "Customer Site Alpha"', "exit", "exit"] if t.family == "EdgeSwitch" else
                    ["configure terminal", "interface Gi1/0/1", "description Customer Site Alpha", "end"])
        assert cmds == expected
    elif t.function == "Access Port":
        assert cmds == ["configure terminal", "interface Gi1/0/1", "switchport", "switchport mode access", "switchport access vlan 4002", "end"]
    elif t.function == "Trunk Port":
        assert cmds == ["configure terminal", "interface Gi1/0/1", "switchport", *(["switchport trunk encapsulation dot1q"] if t.family == "C3750X" else []), "switchport mode trunk", "switchport trunk allowed vlan add 4002", "end"]
    elif t.function == "EVC":
        assert cmds == ["configure terminal", "interface Gi1/0/1", "service instance 10 ethernet", "encapsulation dot1q 4002", "rewrite ingress tag pop 1 symmetric", "bridge-domain 4002", "end"]
    elif t.function == "L2VPN":
        assert cmds == ["configure terminal", "interface Gi1/0/1.10 l2transport", "encapsulation dot1q 4002", "exit", "l2vpn", "bridge group CUSTOMER", "bridge-domain BLUE", "interface Gi1/0/1.10", "end"]
    elif t.function == "VLAN Port":
        assert cmds == ["configure", "interface 0/1", "no vlan tagging 4002", "vlan participation exclude 4002", "exit", "exit"]
    elif t.function == "Subinterface VSI":
        assert cmds == ["system-view", "interface Gi1/0/1.10", "vlan-type dot1q 4002", "l2 binding vsi BLUE", "quit", "quit"]
    with pytest.raises(PlanError):
        request(t.id, {**p, "password": "FORBIDDEN"})
    for required in t.required:
        bad = dict(p)
        del bad[required]
        with pytest.raises(PlanError):
            request(t.id, bad)


def test_dependency_order_rejection_and_digest():
    db, access = template("C3750X", "VLAN Database"), template("C3750X", "Access Port")
    a = request(db.id, inputs(db), sheet_order=1)
    b = request(access.id, inputs(access), sheet_order=2)
    original = plan([b, a], {IP: observed(db)}, now=NOW)
    assert original.to_dict()["results"][1]["dependencies"] == [a["row_id"]]
    approved = review(original, {a["row_id"]: "Approve", b["row_id"]: "Approve"}, expected_digest=original.digest, now=NOW)
    assert all(r["deployment_ready"] for r in approved.to_dict()["results"])
    rejected = review(approved, {a["row_id"]: "Reject"}, expected_digest=approved.digest, now=NOW)
    assert not rejected.to_dict()["results"][1]["deployment_ready"]
    assert len({original.digest, approved.digest, rejected.digest}) == 3
    with pytest.raises(PlanError):
        review(rejected, {}, expected_digest=original.digest)


@pytest.mark.parametrize("family", ["C3750X", "C3850X", "ME3600X", "EdgeSwitch", "NE05E"])
def test_database_rename_noop_and_limits(family):
    t = template(family, "VLAN Database")
    r = request(t.id, inputs(t))
    for name, no_op in (("Customer", True), ("Before", False)):
        obs = observed(t, objects=[VlanObject("vlan", "4002", name)])
        result = plan([r], {IP: obs}, now=NOW).to_dict()["results"][0]
        assert result["no_op"] is no_op
        assert bool(result["commands"]) != no_op
        assert ("VLAN_RENAME_IMPACT" in result["findings"]) != no_op
    for invalid in (0, 4095, True, "100"):
        with pytest.raises(PlanError):
            request(t.id, {**inputs(t), "vlan_id": invalid})
    request(t.id, {**inputs(t), "vlan_id": 1})
    if family in {"C3750X", "C3850X", "ME3600X"}:
        with pytest.raises(PlanError):
            request(t.id, {**inputs(t), "vlan_id": 1002})


def test_missing_and_stale_evidence_fail_closed():
    t = template("C3750X", "VLAN Database")
    r = request(t.id, inputs(t))
    for obs in ({}, {IP: observed(t)}):
        result = plan([r], obs, now=NOW + timedelta(hours=2), decisions={r["row_id"]: "Approve"}).to_dict()["results"][0]
        assert result["commands"] and not result["deployment_ready"]


def test_me_bridge_domain_not_outer_tag_and_ne_existing_vsi():
    t = template("ME3600X", "EVC")
    p = {**inputs(t), "outer_vlan": 123, "bridge_domain": 456}
    r = request(t.id, p)
    obs = observed(t, objects=[VlanObject("vlan", "123")])
    assert "GLOBAL_VLAN_REQUIRED" in plan([r], {IP: obs}, now=NOW).to_dict()["results"][0]["findings"]
    t = template("NE05E", "Subinterface VSI")
    r = request(t.id, inputs(t))
    assert "EXISTING_VSI_REQUIRED" in plan([r], {IP: observed(t)}, now=NOW).to_dict()["results"][0]["findings"]


def test_overlap_and_tampered_commands(tmp_path):
    t = template("C3750X", "Interface Description")
    a, b = request(t.id, inputs(t)), request(t.id, inputs(t), row=4)
    result = plan([a, b], {IP: observed(t)}, now=NOW)
    assert all("ORDERED_RESOURCE_OVERLAP" in r["findings"] for r in result.to_dict()["results"])
    d = result.to_dict()
    d["results"][0]["commands"] = ["erase startup-config"]
    with pytest.raises(PlanError):
        BulkPlan(canonical(d))
    path = tmp_path / "plan.json"
    save(result, path)
    assert load(path).digest == result.digest
    with pytest.raises(FileExistsError):
        save(result, path)


def test_manual_no_network_workbook_and_signed_review(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("network forbidden")
    monkeypatch.setattr(socket, "socket", forbidden)
    from orbitflow.configuration.v2 import observation
    monkeypatch.setattr(observation, "connect_device", forbidden)
    t = template("All", "Manual CLI")
    path = tmp_path / "input.xlsx"
    create_input(path)
    wb = load_workbook(path)
    for col, name in enumerate(t.columns, 1):
        wb[t.sheet].cell(3, col, inputs(t)[name])
    wb.save(path)
    requests = read_input(path)
    spool = observation.collect(requests, {}, None, inventory_path=tmp_path / "inventory.json", spool_root=tmp_path / "spool")
    assert list(observation.observations(spool)) == []
    original = plan(requests, now=NOW)
    output = tmp_path / "review.xlsx"
    export_review(original, output)
    wb = load_workbook(output)
    wb[t.sheet].cell(3, len(t.columns) + len(EXTRA), "Approve")
    wb.save(output)
    approved = import_review(original, output, now=NOW)
    assert approved.to_dict()["results"][0]["commands"] == inputs(t)["commands"]
    assert not approved.to_dict()["results"][0]["deployment_ready"]
    store = ReviewStore(tmp_path / "authority")
    store.decide(approved, "approved", "engineer", now=NOW, expires_at=NOW + timedelta(hours=1))
    assert store.verify(approved, now=NOW)["digest"] == approved.digest
    with pytest.raises(PlanError):
        store.verify(original, now=NOW)
    with pytest.raises(PlanError):
        store.verify(approved, now=NOW + timedelta(hours=2))
    wb[t.sheet].cell(3, 1, "192.0.2.99")
    wb.save(output)
    with pytest.raises(PlanError):
        import_review(original, output, now=NOW)


@pytest.mark.parametrize("text", ["username bob password example", "snmp-server community example", "key-string example", "description secret example"])
def test_manual_secret_rejection(text):
    t = template("All", "Manual CLI")
    with pytest.raises(PlanError):
        request(t.id, {**inputs(t), "commands": text})


def test_shared_live_collection_one_session_and_read_only_commands(tmp_path, monkeypatch):
    from orbitflow.configuration.v2 import observation
    from orbitflow.transport import DeviceCredentials
    from orbitflow.config import ExecutionConfig
    t = template("C3750X", "VLAN Database")
    context = DeviceContext("one", IP, (IP,), "example", "Cisco", "cisco_ios", "C3750X", "C3750X",
                            "c3750x_switching", (), "EXAMPLE", "1", "", NOW, NOW)
    calls, commands = [], []
    session = object()
    @contextmanager
    def connect(ip, credentials, config):
        calls.append(("connect", ip))
        try:
            if ip != IP:
                raise ValueError("must never persist exception text")
            yield session
        finally:
            calls.append(("close", ip))
    class CLI:
        prompt = "example#"
        def __init__(self, supplied):
            assert supplied is session
        def __enter__(self):
            return self
        def __exit__(self, *args):
            calls.append(("cli_closed", IP))
        def require_session(self, supplied):
            assert supplied is session
        def configure(self, **kwargs):
            assert kwargs["paging_command"] == "terminal length 0"
        def run_command(self, command, **kwargs):
            commands.append(command)
            assert command in {"show interfaces description", "show running-config"}
            return ("Interface  Status  Protocol  Description\nGi1/0/1  up  up  Before" if command == "show interfaces description" else
                    "vlan 445\n name Existing\n!\ninterface Gi1/0/1\n description Before\n!\nusername hidden password MUST_NOT_PERSIST")
    class Resolver:
        def __init__(self, store):
            pass
        def resolve(self, supplied, *, management_ip, cli):
            assert supplied is session and management_ip == IP
            calls.append(("resolve", IP))
            return context
    monkeypatch.setattr(observation, "connect_device", connect)
    monkeypatch.setattr(observation, "DeviceCLI", CLI)
    monkeypatch.setattr(observation, "DeviceInventoryResolver", Resolver)
    rows = [request(t.id, inputs(t)), request(t.id, {**inputs(t), "vlan_id": 445}, row=4),
            request(t.id, {**inputs(t), "management_ip": "192.0.2.11"}, row=5)]
    creds = {ip: DeviceCredentials("synthetic-user", "MUST_NOT_PERSIST") for ip in (IP, "192.0.2.11")}
    spool = observation.collect(rows, creds, None, inventory_path=tmp_path / "inv.json", spool_root=tmp_path / "runs",
                                execution_config=ExecutionConfig(1, 0, 0))
    records = dict(observation.observations(spool))
    assert records[IP]["status"] == "live_read_only"
    assert records[IP]["identity"]["inventory_id"] == "one"
    assert records[IP]["evidence"][0]["line"] == 1
    assert records["192.0.2.11"]["status"] == "evidence_unavailable"
    assert commands == ["show interfaces description", "show running-config"]
    assert calls.count(("connect", IP)) == calls.count(("resolve", IP)) == calls.count(("close", IP)) == 1
    assert "MUST_NOT_PERSIST" not in canonical(records)
    assert "must never persist" not in canonical(records)


def test_workbook_order_and_invalid_row_isolation(tmp_path):
    path = tmp_path / "input.xlsx"
    create_input(path)
    book = load_workbook(path)
    db = template("C3750X", "VLAN Database")
    ac = template("C3750X", "Access Port")
    for t in (db, ac):
        for col, field in enumerate(t.columns, 1):
            book[t.sheet].cell(3, col, inputs(t).get(field))
    book[db.sheet].cell(4, 1, "bad target")
    book.move_sheet(ac.sheet, offset=-1)
    book.save(path)
    rows = read_input(path)
    assert len(rows) == 2 and len(rows.errors) == 1
    assert rows[0]["template_id"] == ac.id
    result = plan(rows, {IP: observed(db)}, now=NOW)
    assert "GLOBAL_VLAN_REQUIRED" in result.to_dict()["results"][0]["findings"]
    output = tmp_path / "review.xlsx"
    export_review(result, output)
    review_book = load_workbook(output)
    assert review_book.sheetnames[:23] == book.sheetnames
    assert review_book[db.sheet]["A4"].value.startswith("Invalid input omitted")
    assert "bad target" not in canonical(result.to_dict())
    assert import_review(result, output, now=NOW).digest == result.digest


@pytest.mark.parametrize("family", ["ASR920", "ME3600X"])
@pytest.mark.parametrize("enc,outer,inner,pop,expected", [
    ("untagged", None, None, None, "encapsulation untagged"),
    ("QinQ", 445, 545, 2, "encapsulation dot1q 445 second-dot1q 545"),
])
def test_evc_encapsulation_variants(family, enc, outer, inner, pop, expected):
    t = template(family, "EVC")
    p = inputs(t)
    p.update(encapsulation=enc, outer_vlan=outer, inner_vlan=inner, pop_tags=pop)
    result = plan([request(t.id, p)], {IP: observed(t)}, now=NOW).to_dict()["results"][0]
    assert expected in result["commands"]
    if pop:
        assert "rewrite ingress tag pop 2 symmetric" in result["commands"]


def test_asr_global_binding_and_evc_noop_from_shared_facts():
    from orbitflow.vendors.configuration_facts import observe_configuration
    t = template("ASR920", "EVC")
    p = {**inputs(t), "outer_vlan": 445, "bridge_domain": 445}
    obs = observed(t)
    config = "interface Gi1/0/1\n service instance 10 ethernet\n  encapsulation dot1q 445\n  rewrite ingress tag pop 1 symmetric\n  bridge-domain 445"
    obs["facts"] = safe_data([asdict(n) for n in observe_configuration(config, "cisco_xe")])
    r = request(t.id, p)
    result = plan([r], {IP: obs}, now=NOW).to_dict()["results"][0]
    assert result["no_op"] and result["commands"] == []
    obs["audit"][0]["numeric_mappings"] = [{"global_bridge_domain": ["445"]}]
    result = plan([r], {IP: obs}, now=NOW, decisions={r["row_id"]: "Approve"}).to_dict()["results"][0]
    assert "ASR920_GLOBAL_BINDING_CONFLICT" in result["findings"]
    assert not result["deployment_ready"]


def test_edge_access_add_replace_and_description_preservation():
    t = template("EdgeSwitch", "VLAN Port")
    p = {**inputs(t), "action": "Add", "mode": "Access", "vlans": [445]}
    result = plan([request(t.id, p)], {IP: observed(t)}, now=NOW).to_dict()["results"][0]
    assert "vlan participation include 445" in result["commands"]
    assert "vlan pvid 445" in result["commands"]
    assert not any("disable" in c or "description" in c for c in result["commands"])
    with pytest.raises(PlanError):
        request(t.id, {**p, "vlans": [4094]})


def test_secret_bearing_evidence_and_fields_rejected():
    t = template("C3750X", "VLAN Database")
    r, obs = request(t.id, inputs(t)), observed(t)
    obs["evidence"][0]["excerpt"] = "password DO_NOT_PERSIST"
    with pytest.raises(PlanError):
        plan([r], {IP: obs}, now=NOW)
    obs = observed(t)
    obs["identity"]["password"] = "DO_NOT_PERSIST"
    with pytest.raises(PlanError):
        plan([r], {IP: obs}, now=NOW)


def test_planning_numeric_scope_does_not_change_audit():
    from orbitflow.vendors.configuration_facts import observe_configuration
    from orbitflow.compliance.resolvers import resolver_for
    context = DeviceContext("one", IP, (IP,), "example", "Cisco", "cisco_xr", "NCS540", "NCS540",
                            "", (), "EXAMPLE", "1", "", NOW, NOW)
    config = ("interface Gi0/0/0/1\n!\ninterface Gi0/0/0/1.10 l2transport\n encapsulation dot1q 4094\n!\n"
              "l2vpn\n bridge group G\n  bridge-domain arbitrary\n   interface Gi0/0/0/1.10")
    state = VlanState("example", IP, "cisco_xr", (), (), NOW, observe_configuration(config, "cisco_xr"))
    factory = resolver_for(context)
    before = factory(context, state).result()
    planning = factory(context, state, planning=True).result()
    assert planning["valid_database_vlans"] == [4094]
    assert before["valid_database_vlans"] == []
    assert factory(context, state).result() == before


def test_ne_tagged_vsi_planning_relationship_preserves_audit():
    from orbitflow.vendors.configuration_facts import observe_configuration
    from orbitflow.compliance.resolvers import resolver_for
    context = DeviceContext("one", IP, (IP,), "example", "Huawei", "huawei_vrp", "NE05E", "NE05E",
                            "", (), "EXAMPLE", "1", "", NOW, NOW)
    config = "vsi BLUE\n#\ninterface GE0/1\n#\ninterface GE0/1.10\n vlan-type dot1q 4094\n l2 binding vsi BLUE"
    state = VlanState("example", IP, "huawei_vrp", (), (VlanObject("vsi", "BLUE"),), NOW, observe_configuration(config, "huawei_vrp"))
    factory = resolver_for(context)
    before = factory(context, state).result()
    assert factory(context, state, planning=True).result()["valid_database_vlans"] == [4094]
    assert factory(context, state).result() == before


def test_review_authority_tamper_and_rejection(tmp_path):
    import sqlite3
    t = template("All", "Manual CLI")
    r = request(t.id, inputs(t))
    result = plan([r], decisions={r["row_id"]: "Approve"}, now=NOW)
    store = ReviewStore(tmp_path / "authority")
    store.decide(result, "approved", "engineer", now=NOW, expires_at=NOW + timedelta(hours=1))
    store.decide(result, "rejected", "engineer", now=NOW)
    with pytest.raises(PlanError):
        store.verify(result, now=NOW)
    with sqlite3.connect(store.root / "approvals.sqlite3") as db:
        db.execute("UPDATE decisions SET signature = 'bad' WHERE sequence = 2")
    with pytest.raises(PlanError):
        store.verify(result, now=NOW)


def test_all_template_workbook_roundtrip_preserves_input_values(tmp_path):
    path = tmp_path / "mixed.xlsx"
    create_input(path)
    book = load_workbook(path)
    for t in CATALOGUE:
        p = inputs(t)
        if "vlans" in p:
            p["vlans"] = "4002-4003"
        for col, field in enumerate(t.columns, 1):
            book[t.sheet].cell(3, col, p.get(field))
    book.save(path)
    rows = read_input(path)
    assert len(rows) == 22 and not rows.errors
    result = plan(rows, now=NOW)
    output = tmp_path / "review.xlsx"
    export_review(result, output)
    returned = load_workbook(output)
    t = template("C3750X", "Trunk Port")
    assert returned[t.sheet].cell(3, t.columns.index("vlans") + 1).value == "4002-4003"
    assert import_review(result, output, now=NOW).digest == result.digest


def test_manual_cli_operator_commands_offline(tmp_path, monkeypatch):
    from orbitflow.configuration.v2.cli import main
    def forbidden(*args, **kwargs):
        raise AssertionError("no network or credential prompting")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr("orbitflow.configuration.v2.cli.getpass", forbidden)
    source = tmp_path / "source.xlsx"
    main(["input", str(source)])
    book = load_workbook(source)
    t = template("All", "Manual CLI")
    for col, field in enumerate(t.columns, 1):
        book[t.sheet].cell(3, col, inputs(t)[field])
    book.save(source)
    output = tmp_path / "plan.json"
    main(["plan", str(source), str(output)])
    original = load(output)
    assert original.to_dict()["source"].startswith("workbook-sha256:")
    book = load_workbook(output.with_suffix(".xlsx"))
    book[t.sheet].cell(3, len(t.columns) + len(EXTRA), "Approve")
    book.save(output.with_suffix(".xlsx"))
    reviewed = tmp_path / "reviewed.json"
    authority = tmp_path / "authority"
    main(["review", str(output), str(output.with_suffix(".xlsx")), str(reviewed), "--actor", "engineer", "--authority", str(authority)])
    assert ReviewStore(authority).verify(load(reviewed))["execution_authorized"] is False


def test_mixed_device_workbook_evidence_and_manual_status(tmp_path):
    templates = [template("C3750X", "VLAN Database"), template("NE05E", "VLAN Database"), template("All", "Manual CLI")]
    source = tmp_path / "input.xlsx"
    create_input(source)
    book = load_workbook(source)
    observations = {}
    for index, t in enumerate(templates):
        ip = f"192.0.2.{index + 10}"
        p = {**inputs(t), "management_ip": ip}
        for col, field in enumerate(t.columns, 1):
            book[t.sheet].cell(3, col, p.get(field))
        if t.family != "All":
            obs = observed(t, objects=[VlanObject("vlan", "4002", "Before")])
            obs["identity"].update(management_ip=ip, inventory_id=f"device-{index}", hostname=f"device-{index}", serial_number=f"EXAMPLE-{index}")
            observations[ip] = obs
    book.save(source)
    result = plan(read_input(source), observations, now=NOW)
    destination = tmp_path / "review.xlsx"
    export_review(result, destination)
    book = load_workbook(destination)
    for t in templates:
        sheet = book[t.sheet]
        status = sheet.cell(3, len(t.columns) + EXTRA.index("Live Validation") + 1).value
        evidence = sheet.cell(3, len(t.columns) + EXTRA.index("Existing Evidence") + 1).value
        assert status == ("not_live_validated" if t.family == "All" else "live_read_only")
        assert not evidence if t.family == "All" else evidence.startswith("interface ")
    assert len(result.to_dict()["observations"]) == 2


@pytest.mark.parametrize("family", ["C3750X", "C3850X"])
@pytest.mark.parametrize("action,fragment", [("Add", "add "), ("Remove", "remove "), ("Replace", "")])
def test_trunk_actions(family, action, fragment):
    t = template(family, "Trunk Port")
    p = {**inputs(t), "action": action, "native_vlan": 445}
    result = plan([request(t.id, p)], {IP: observed(t)}, now=NOW).to_dict()["results"][0]
    assert f"switchport trunk allowed vlan {fragment}4002" in result["commands"]
    assert "switchport trunk native vlan 445" in result["commands"]
    assert ("MEMBERSHIP_STATE_UNKNOWN" in result["findings"]) == (action != "Replace")


def test_edge_replace_removes_prior_membership():
    t = template("EdgeSwitch", "VLAN Port")
    p = {**inputs(t), "action": "Replace", "vlans": [545]}
    obs = observed(t)
    obs["vlans"] = [dict(interface_name="0/1", mode="trunk", tagged_vlans=[445], referenced_vlans=[445], pvid=None)]
    obs["audit"][0].update(configured_membership_vlans=[445], configured_tagged_vlans=[445])
    result = plan([request(t.id, p)], {IP: obs}, now=NOW).to_dict()["results"][0]
    assert result["commands"] == ["configure", "interface 0/1", "no vlan tagging 445", "vlan participation exclude 445",
                                  "vlan participation include 545", "vlan tagging 545", "exit", "exit"]


def test_vendor_secret_marker_sanitized_before_spooling():
    t = template("NE05E", "VLAN Database")
    obs = observed(t, objects=[VlanObject("vlan", "4002", "cipher UNDISCLOSED")])
    assert "UNDISCLOSED" not in canonical(obs)
    assert "[REDACTED]" in canonical(obs)


def configuration_observation(t, config, *, objects=()):
    from orbitflow.vendors.configuration_facts import observe_configuration
    obs = observed(t, objects=objects)
    obs["facts"] = safe_data([asdict(n) for n in observe_configuration(config, FAMILIES[t.family][0])])
    obs["evidence"][0]["excerpt"] = config
    return obs


@pytest.mark.parametrize("enc,tags,command", [
    ("dot1q", {"outer_vlan": 445}, "encapsulation dot1q 445"),
    ("QinQ", {"outer_vlan": 445, "inner_vlan": 545}, "encapsulation dot1q 445 second-dot1q 545"),
    ("untagged", {}, "encapsulation untagged"),
])
def test_ncs_encapsulation_review_and_noop(enc, tags, command, tmp_path):
    t = template("NCS540", "L2VPN")
    p = {k: v for k, v in inputs(t).items() if k != "outer_vlan"}
    p.update(encapsulation=enc, **tags)
    config = f"interface Gi1/0/1.10 l2transport\n {command}\n!\nl2vpn\n bridge group CUSTOMER\n  bridge-domain BLUE\n   interface Gi1/0/1.10"
    obs = configuration_observation(t, config)
    r = request(t.id, p)
    result = plan([r], {IP: obs}, now=NOW)
    assert result.to_dict()["results"][0]["no_op"]
    assert result.to_dict()["results"][0]["commands"] == []
    obs = observed(t)
    result = plan([r], {IP: obs}, now=NOW)
    assert command in result.to_dict()["results"][0]["commands"]
    review_path = tmp_path / "review.xlsx"
    export_review(result, review_path)
    assert import_review(result, review_path, now=NOW).digest == result.digest
    # A competing subinterface claiming this ingress is reviewable but blocked.
    obs = configuration_observation(t, config.replace(".10", ".11"))
    row = plan([r], {IP: obs}, now=NOW, decisions={r["row_id"]: "Approve"}).to_dict()["results"][0]
    assert "INGRESS_TAG_OVERLAP" in row["findings"] and not row["deployment_ready"]


@pytest.mark.parametrize("enc,tags", [
    ("untagged", {"outer_vlan": 445}), ("dot1q", {}),
    ("dot1q", {"outer_vlan": 445, "inner_vlan": 545}),
    ("QinQ", {"outer_vlan": 445}),
])
def test_ncs_conditional_vlan_validation(enc, tags):
    t = template("NCS540", "L2VPN")
    p = {k: v for k, v in inputs(t).items() if k != "outer_vlan"}
    with pytest.raises(PlanError):
        request(t.id, {**p, "encapsulation": enc, **tags})


@pytest.mark.parametrize("choice,enc,tags,rewrite", [
    ("None", "dot1q", {"outer_vlan": 445}, ""),
    ("Pop1", "dot1q", {"outer_vlan": 445}, "rewrite ingress tag pop 1 symmetric"),
    ("Pop2", "QinQ", {"outer_vlan": 445, "inner_vlan": 545}, "rewrite ingress tag pop 2 symmetric"),
    ("Push", "untagged", {"push_vlan": 445}, "rewrite ingress tag push dot1q 445 symmetric"),
])
def test_asr_rewrite_render_noop_and_explicit_none(choice, enc, tags, rewrite):
    t = template("ASR920", "EVC")
    p = {k: v for k, v in inputs(t).items() if k not in {"pop_tags", "outer_vlan"}}
    p.update(encapsulation=enc, rewrite=choice, **tags)
    encapsulation = "encapsulation untagged" if enc == "untagged" else "encapsulation dot1q 445" + (" second-dot1q 545" if enc == "QinQ" else "")
    config = f"interface Gi1/0/1\n service instance 10 ethernet\n  {encapsulation}\n  {rewrite}\n  bridge-domain 4002"
    obs = configuration_observation(t, config)
    r = request(t.id, p)
    assert plan([r], {IP: obs}, now=NOW).to_dict()["results"][0]["no_op"]
    row = plan([r], {IP: observed(t)}, now=NOW).to_dict()["results"][0]
    assert (rewrite or "no rewrite ingress tag") in row["commands"]
    # An omitted rewrite cannot silently preserve an existing operation.
    if rewrite:
        omitted = {k: v for k, v in p.items() if k not in {"rewrite", "push_vlan"}}
        r = request(t.id, omitted)
        row = plan([r], {IP: obs}, now=NOW, decisions={r["row_id"]: "Approve"}).to_dict()["results"][0]
        assert "PRESERVED_REWRITE_REQUIRES_REVIEW" in row["findings"]
        assert not row["no_op"] and not row["deployment_ready"]


@pytest.mark.parametrize("family,enc,choice,extra", [
    ("ASR920", "untagged", "Pop1", {}), ("ASR920", "dot1q", "Pop2", {}),
    ("ASR920", "dot1q", "Push", {"push_vlan": 445}),
    ("ME3600X", "untagged", "Push", {"push_vlan": 445}),
    ("ASR920", "untagged", "Push", {}),
    ("ASR920", "dot1q", "None", {"pop_tags": 1}),
])
def test_rewrite_compatibility(family, enc, choice, extra):
    t = template(family, "EVC")
    p = {k: v for k, v in inputs(t).items() if k != "pop_tags" and (enc != "untagged" or k != "outer_vlan")}
    with pytest.raises(PlanError):
        request(t.id, {**p, "encapsulation": enc, "rewrite": choice, **extra})


def edge_observation():
    t = template("EdgeSwitch", "VLAN Port")
    obs = observed(t, objects=[VlanObject("vlan", str(v)) for v in (445, 545, 645)])
    obs["vlans"] = [dict(interface_name="0/1", mode="hybrid", tagged_vlans=[545], referenced_vlans=[445, 545], pvid=445)]
    obs["audit"][0].update(configured_membership_vlans=[445, 545], configured_tagged_vlans=[545])
    return obs


@pytest.mark.parametrize("participates", [False, True])
def test_edge_pvid_only_membership_and_review_readiness(participates):
    t = template("EdgeSwitch", "VLAN Port")
    obs = edge_observation()
    if participates:
        obs["audit"][0]["configured_membership_vlans"].append(645)
    r = request(t.id, dict(management_ip=IP, interface="0/1", pvid=645))
    pending = plan([r], {IP: obs}, now=NOW)
    row = pending.to_dict()["results"][0]
    expected = ["configure", "interface 0/1"]
    if not participates:
        expected.append("vlan participation include 645")
    expected += ["vlan pvid 645", "exit", "exit"]
    assert row["commands"] == expected
    assert row["consistency"] == "consistent" and not row["deployment_ready"]
    for decision in ("Approve", "Reject"):
        reviewed = review(pending, {r["row_id"]: decision}, expected_digest=pending.digest, now=NOW)
        result = reviewed.to_dict()["results"][0]
        assert result["deployment_ready"] == (decision == "Approve")
        assert result["commands"] == expected


def test_edge_pvid_without_membership_is_not_noop():
    t = template("EdgeSwitch", "VLAN Port")
    obs = edge_observation()
    obs["vlans"][0]["pvid"] = 645
    r = request(t.id, dict(management_ip=IP, interface="0/1", pvid=645))
    row = plan([r], {IP: obs}, now=NOW).to_dict()["results"][0]
    assert not row["no_op"]
    assert "vlan participation include 645" in row["commands"]


def test_edge_independent_pvid_replace_and_conflicts():
    t = template("EdgeSwitch", "VLAN Port")
    p = dict(management_ip=IP, interface="0/1", pvid=645)
    r = request(t.id, p)
    row = plan([r], {IP: edge_observation()}, now=NOW).to_dict()["results"][0]
    assert row["commands"] == ["configure", "interface 0/1", "vlan participation include 645", "vlan pvid 645", "exit", "exit"]
    r = request(t.id, {**p, "pvid": 445})
    assert plan([r], {IP: edge_observation()}, now=NOW).to_dict()["results"][0]["no_op"]
    p.update(action="Replace", vlans=[645])
    r = request(t.id, p)
    row = plan([r], {IP: edge_observation()}, now=NOW).to_dict()["results"][0]
    assert "vlan participation exclude 445" not in row["commands"]
    assert row["commands"].index("no vlan tagging 545") < row["commands"].index("vlan participation exclude 545")
    r = request(t.id, {**p, "replace_untagged": "Yes"})
    row = plan([r], {IP: edge_observation()}, now=NOW).to_dict()["results"][0]
    assert "vlan participation exclude 445" in row["commands"]
    assert "UNTAGGED_REPLACEMENT_IMPACT" in row["findings"]
    r = request(t.id, {**p, "mode": "Access", "vlans": [545], "pvid": 545})
    row = plan([r], {IP: edge_observation()}, now=NOW, decisions={r["row_id"]: "Approve"}).to_dict()["results"][0]
    assert {"ACCESS_CONVERSION_IMPACT", "ACCESS_TAGGING_CONFLICT"} <= set(row["findings"])
    assert not row["deployment_ready"]
    assert not any("disable" in c for c in row["commands"])


@pytest.mark.parametrize("case", ["ncs_untagged", "ncs_qinq", "asr_push", "asr_none", "asr_pop2", "edge_pvid", "edge_replace", "c3850_name"])
def test_revised_options_input_review_roundtrip(case, tmp_path):
    if case.startswith("ncs"):
        t = template("NCS540", "L2VPN")
        p = {k: v for k, v in inputs(t).items() if k != "outer_vlan"}
        p.update(encapsulation="untagged" if case.endswith("untagged") else "QinQ")
        if p["encapsulation"] == "QinQ":
            p.update(outer_vlan=445, inner_vlan=545)
    elif case.startswith("asr"):
        t = template("ASR920", "EVC")
        p = {k: v for k, v in inputs(t).items() if k not in {"outer_vlan", "pop_tags"}}
        if case == "asr_push":
            p.update(encapsulation="untagged", rewrite="Push", push_vlan=445)
        elif case == "asr_pop2":
            p.update(encapsulation="QinQ", outer_vlan=445, inner_vlan=545, rewrite="Pop2")
        else:
            p.update(outer_vlan=445, rewrite="None")
    elif case.startswith("edge"):
        t = template("EdgeSwitch", "VLAN Port")
        p = dict(management_ip=IP, interface="0/1", pvid=645)
        if case.endswith("replace"):
            p.update(action="Replace", mode="Tagged", vlans="645")
    else:
        t = template("C3850X", "VLAN Database")
        p = {**inputs(t), "name": "Customer Site Alpha"}
    source = tmp_path / "input.xlsx"
    create_input(source)
    book = load_workbook(source)
    for col, field in enumerate(t.columns, 1):
        book[t.sheet].cell(3, col, p.get(field))
    book.save(source)
    rows = read_input(source)
    assert len(rows) == 1 and not rows.errors
    obs = edge_observation() if t.family == "EdgeSwitch" else observed(t)
    result = plan(rows, {IP: obs}, now=NOW)
    output = tmp_path / "review.xlsx"
    export_review(result, output)
    book = load_workbook(output)
    sheet = book[t.sheet]
    for col, field in enumerate(t.columns, 1):
        assert sheet.cell(3, col).value == (str(p[field]) if field in p else None)
    assert sheet.cell(3, len(t.columns) + EXTRA.index("Existing Evidence") + 1).value == obs["evidence"][0]["excerpt"]
    assert sheet.cell(3, len(t.columns) + EXTRA.index("Proposed CLI") + 1).value
    sheet.cell(3, len(t.columns) + len(EXTRA), "Approve")
    book.save(output)
    approved = import_review(result, output, now=NOW)
    assert approved.digest != result.digest
    assert not approved.to_dict()["results"][0]["execution_authorized"]
    # Approval cannot turn failed evidence into readiness, even for valid inputs.
    unavailable = plan(rows, now=NOW)
    output = tmp_path / "unavailable.xlsx"
    export_review(unavailable, output)
    book = load_workbook(output)
    book[t.sheet].cell(3, len(t.columns) + len(EXTRA), "Approve")
    book.save(output)
    assert not import_review(unavailable, output, now=NOW).to_dict()["results"][0]["deployment_ready"]


def test_c3850_space_name_rename_and_noop():
    t = template("C3850X", "VLAN Database")
    p = {**inputs(t), "name": "Customer Site Alpha"}
    r = request(t.id, p)
    obs = observed(t, objects=[VlanObject("vlan", "4002", "Before")])
    row = plan([r], {IP: obs}, now=NOW).to_dict()["results"][0]
    assert "name Customer Site Alpha" in row["commands"]
    assert "VLAN_RENAME_IMPACT" in row["findings"]
    obs = observed(t, objects=[VlanObject("vlan", "4002", p["name"])])
    assert plan([r], {IP: obs}, now=NOW).to_dict()["results"][0]["no_op"]


@pytest.mark.parametrize("action,vlans", [("Add", [545]), ("Replace", [545]), ("Remove", [645])])
def test_edge_tagged_noops_preserve_untagged(action, vlans):
    t = template("EdgeSwitch", "VLAN Port")
    r = request(t.id, dict(management_ip=IP, interface="0/1", action=action, vlans=vlans))
    row = plan([r], {IP: edge_observation()}, now=NOW).to_dict()["results"][0]
    assert row["no_op"] and row["commands"] == []


def test_edge_proposed_tagging_cannot_tag_preserved_pvid():
    t = template("EdgeSwitch", "VLAN Port")
    r = request(t.id, dict(management_ip=IP, interface="0/1", action="Add", vlans=[445]))
    row = plan([r], {IP: edge_observation()}, now=NOW, decisions={r["row_id"]: "Approve"}).to_dict()["results"][0]
    assert "PVID_TAGGING_CONFLICT" in row["findings"] and not row["deployment_ready"]


def test_revised_cli_review_and_digest_invalidation(tmp_path, monkeypatch):
    from orbitflow.configuration.v2.cli import main
    monkeypatch.setattr(socket, "socket", lambda *a, **kw: pytest.fail("review connected"))
    t = template("ASR920", "EVC")
    p = {k: v for k, v in inputs(t).items() if k not in {"outer_vlan", "pop_tags"}}
    p.update(encapsulation="untagged", rewrite="Push", push_vlan=445)
    r = request(t.id, p)
    result = plan([r], {IP: observed(t)}, now=NOW)
    source, workbook, output = tmp_path / "plan.json", tmp_path / "review.xlsx", tmp_path / "reviewed.json"
    save(result, source)
    export_review(result, workbook)
    book = load_workbook(workbook)
    book[t.sheet].cell(3, len(t.columns) + len(EXTRA), "Reject")
    book.save(workbook)
    main(["review", str(source), str(workbook), str(output), "--actor", "engineer", "--authority", str(tmp_path / "authority")])
    revised = load(output)
    assert revised.digest != result.digest
    assert revised.to_dict()["results"][0]["decision"] == "Reject"
    assert "rewrite ingress tag push dot1q 445 symmetric" in revised.to_dict()["results"][0]["commands"]
    assert not revised.to_dict()["results"][0]["deployment_ready"]
