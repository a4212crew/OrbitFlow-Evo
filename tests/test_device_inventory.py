from __future__ import annotations

import json
import itertools
from datetime import datetime, timezone

import pytest

from orbitflow.inventory import DeviceInventoryError, DeviceInventoryResolver, JsonInventoryStore


NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)


class Runner:
    def __init__(self, outputs, prompt="device#"):
        self.outputs = outputs
        self.prompt = prompt
        self.commands = []

    def run_command(self, command, timeout=10.0):
        self.commands.append(command)
        value = self.outputs.get(command, "% Invalid input detected")
        if isinstance(value, Exception):
            raise value
        return value


def resolver(tmp_path, outputs, ids=None, prompt="device#"):
    ids = ids or (f"id-{number}" for number in itertools.count(1))
    store = JsonInventoryStore(tmp_path / "inventory.json", id_factory=lambda: next(ids))
    return DeviceInventoryResolver(store, clock=lambda: NOW, runner_factory=lambda _: Runner(outputs, prompt)), store


@pytest.mark.parametrize(
    "version,inventory,family,hardware_model,platform,profile",
    [
        ("Cisco IOS XE Software, Version 17.06.07\nedge uptime is 2 weeks\ncisco ASR920 processor", 'NAME: "Chassis", DESCR: "ASR 920 chassis"\nPID: ASR-920-24SZ-M, VID: V01, SN: CAT1', "ASR920", "ASR-920-24SZ-M", "cisco_xe", "asr920_evc"),
        ("Cisco IOS XE Software, Version 16.12\nsw uptime is 1 day\nModel Number : WS-C3850-12XS", "SN: CAT2", "C3850", "WS-C3850-12XS", "cisco_xe", "c3850_switching"),
        ("Cisco IOS Software, Version 15.2\nsw2 uptime is 4 days\nWS-C3750X", "NAME: chassis\nPID: WS-C3750X-48T-S, VID: V02\nSN: CAT3", "C3750X", "WS-C3750X-48T-S", "cisco_ios", "c3750x_switching"),
        ("Cisco IOS Software, Version 15.3\nmetro uptime is 3 weeks\nME-3600X", "NAME: chassis\nPID: ME-3600X-24FS-M, VID: V01\nSN: CAT4", "ME3600X", "ME-3600X-24FS-M", "cisco_ios", "me3600x_evc"),
        ("Cisco IOS XR Software, Version 7.7.2\ncore uptime is 1 year\ncisco N540X-6Z18G-SYS-D processor", "Serial Num Rack Num Rack Type Rack State Data Plane State\nFOC2643NCVA 0 NCS540-RTR Active On", "NCS540", "N540X-6Z18G-SYS-D", "cisco_xr", "ncs540_l2"),
    ],
)
def test_captured_cisco_outputs_detect_family_model_and_profile(tmp_path, version, inventory, family, hardware_model, platform, profile):
    details_command = "show chassis" if family == "NCS540" else "show inventory"
    service, _ = resolver(tmp_path, {"show version": version, details_command: inventory})
    context = service.resolve(object(), management_ip="192.0.2.1")
    assert (context.device_family, context.platform, context.capability_profile) == (family, platform, profile)
    assert context.hardware_model == hardware_model
    if family == "ME3600X":
        assert "evc" in context.capability_flags
    if family == "NCS540":
        assert context.serial_number == "FOC2643NCVA"


def test_cisco_family_detection_retains_observed_generic_model(tmp_path):
    outputs = {"show version": "Cisco IOS XE Software, Version 17.06.07\nedge uptime is 2 weeks\nASR920", "show inventory": "SN: CAT1"}
    service, _ = resolver(tmp_path, outputs)
    context = service.resolve(object(), management_ip="192.0.2.5")
    assert context.device_family == "ASR920"
    assert context.hardware_model == "ASR920"


def test_ncs540_show_chassis_accepts_live_dashed_separator(tmp_path):
    version = "Cisco IOS XR Software, Version 7.7.2\ncore uptime is 1 year\nNCS-540"
    chassis = """Serial Num    Rack Num    Rack Type   Rack State
-------------------------------------------------
FOC2643NCN3   0           LCC         UP

"""
    service, _ = resolver(
        tmp_path, {"show version": version, "show chassis": chassis}
    )

    context = service.resolve(object(), management_ip="192.0.2.4")

    assert context.serial_number == "FOC2643NCN3"


@pytest.mark.parametrize(
    ("esn_output", "expected_serial"),
    [
        ("ESN : 2102350ABC", "2102350ABC"),
        ("ESN of master:2102350DYT10K1000045", "2102350DYT10K1000045"),
        ("Serial Number : NE05ESERIAL1", "NE05ESERIAL1"),
    ],
)
def test_captured_huawei_ne05e_output(tmp_path, esn_output, expected_serial):
    outputs = {"show version": "% Unknown command", "screen-length 0 temporary": "",
               "display version": "Huawei Versatile Routing Platform Software\nVRP (R) software, Version 8.180\nNE05E-S2 uptime is 9 days",
               "display esn": esn_output}
    service, _ = resolver(tmp_path, outputs, prompt="<VIC-RICH-REGEN-RTR1>")
    context = service.resolve(object(), management_ip="192.0.2.2")
    assert (context.platform, context.device_family, context.serial_number) == ("huawei_vrp", "NE05E", expected_serial)
    assert context.hostname == "VIC-RICH-REGEN-RTR1"


def test_captured_edgeswitch_output(tmp_path):
    outputs = {"show version": "Ubiquiti EdgeSwitch\nMachine Model...................... EdgeSwitch 48\nSerial Number...................... ES123\nSoftware Version................... 1.10.3\nSystem Up Time..................... 12 days"}
    runner = Runner(outputs, prompt="(access-sw) #")
    store = JsonInventoryStore(tmp_path / "inventory.json", id_factory=lambda: "edge-id")
    service = DeviceInventoryResolver(store, clock=lambda: NOW, runner_factory=lambda _: runner)
    context = service.resolve(object(), management_ip="192.0.2.3")
    assert (context.platform, context.device_family, context.hardware_model) == ("ubiquiti_edgeswitch", "EdgeSwitch", "EdgeSwitch 48")
    assert context.hostname == "access-sw"
    assert runner.commands == ["show version"]


def test_same_serial_new_ip_reuses_identity(tmp_path):
    outputs = {"show version": "Cisco IOS Software, Version 15.2\none uptime is 1 day\nWS-C3750X", "show inventory": "SN: SAME"}
    service, store = resolver(tmp_path, outputs)
    first = service.resolve(object(), management_ip="192.0.2.10")
    before = store.contexts()
    before_events = service.last_events
    second = service.resolve(object(), management_ip="192.0.2.11")
    assert len(before) == 1
    assert before_events == ()
    assert before[0].device_id == first.device_id
    assert before[0].serial_number == "SAME"
    assert before[0].management_ip == "192.0.2.10"
    assert before[0].observed_management_ips == ("192.0.2.10",)
    assert second.device_id == first.device_id
    assert second.serial_number == "SAME"
    assert second.management_ip == "192.0.2.11"
    assert second.observed_management_ips == ("192.0.2.10", "192.0.2.11")
    assert service.last_events == ("management_ip_changed",)
    assert len(store.contexts()) == 1


def test_same_ip_new_serial_keeps_physical_identities_separate(tmp_path):
    ids = iter(("one", "two"))
    first_outputs = {"show version": "Cisco IOS Software, Version 15.2\nshared uptime is 1 day\nWS-C3750X", "show inventory": "SN: OLD"}
    service, store = resolver(tmp_path, first_outputs, ids)
    first = service.resolve(object(), management_ip="192.0.2.20")
    before = store.contexts()
    before_events = service.last_events
    service._runner_factory = lambda _: Runner({**first_outputs, "show inventory": "SN: NEW"})
    second = service.resolve(object(), management_ip="192.0.2.20")
    assert len(before) == 1
    assert before_events == ()
    assert before[0].device_id == first.device_id == "one"
    assert before[0].serial_number == "OLD"
    assert before[0].management_ip == "192.0.2.20"
    assert before[0].observed_management_ips == ("192.0.2.20",)
    assert second.device_id == "two"
    assert second.device_id != first.device_id
    assert second.serial_number == "NEW"
    assert second.management_ip == "192.0.2.20"
    assert second.observed_management_ips == ("192.0.2.20",)
    assert set(service.last_events) == {"likely_replacement_or_ip_reassignment", "hostname_collision"}
    assert len(store.contexts()) == 2


def test_same_ip_later_serial_safely_enriches_existing_identity(tmp_path):
    ids = iter(("one", "unused"))
    outputs = {"show version": "Cisco IOS Software, Version 15.2\nshared uptime is 1 day\nWS-C3750X", "show inventory": "no serial reported"}
    service, store = resolver(tmp_path, outputs, ids)
    first = service.resolve(object(), management_ip="192.0.2.30")
    before = store.contexts()
    before_events = service.last_events
    service._runner_factory = lambda _: Runner({**outputs, "show inventory": "SN: DISCOVERED"})
    enriched = service.resolve(object(), management_ip="192.0.2.30")
    assert len(before) == 1
    assert before_events == ()
    assert before[0].device_id == first.device_id == "one"
    assert before[0].serial_number == ""
    assert before[0].management_ip == "192.0.2.30"
    assert before[0].observed_management_ips == ("192.0.2.30",)
    assert enriched.device_id == first.device_id
    assert enriched.serial_number == "DISCOVERED"
    assert enriched.management_ip == "192.0.2.30"
    assert enriched.observed_management_ips == ("192.0.2.30",)
    assert service.last_events == ("serial_number_discovered",)
    assert len(store.contexts()) == 1


def test_repeated_missing_serial_and_matching_hostname_model_do_not_merge(tmp_path):
    ids = iter(("one", "two"))
    outputs = {"show version": "Cisco IOS Software, Version 15.2\nshared uptime is 1 day\nWS-C3750X", "show inventory": "no serial reported"}
    service, store = resolver(tmp_path, outputs, ids)
    third = service.resolve(object(), management_ip="192.0.2.30")
    fourth = service.resolve(object(), management_ip="192.0.2.30")
    assert third.device_id != fourth.device_id
    assert service.last_events == ()
    assert len(store.contexts()) == 2


def test_failure_preserves_success_and_never_persists_secrets(tmp_path):
    outputs = {"show version": "Cisco IOS Software, Version 15.2\nsafe uptime is 1 day\nWS-C3750X", "show inventory": "SN: SAFE1"}
    service, store = resolver(tmp_path, outputs)
    original = service.resolve(object(), management_ip="192.0.2.40")
    service._runner_factory = lambda _: Runner({"show version": RuntimeError("password=hunter2")})
    with pytest.raises(DeviceInventoryError, match="RuntimeError"):
        service.resolve(object(), management_ip="192.0.2.40")
    retained = store.contexts()[0]
    assert retained.serial_number == original.serial_number
    assert retained.last_successful_collection == original.last_successful_collection
    assert retained.collection_status == "failed"
    assert "hunter2" not in (tmp_path / "inventory.json").read_text()


def test_unknown_ambiguous_and_override(tmp_path):
    service, _ = resolver(tmp_path, {"show version": "nothing", "screen-length 0 temporary": "", "display version": "nothing"})
    with pytest.raises(DeviceInventoryError, match="unknown or ambiguous"):
        service.resolve(object(), management_ip="192.0.2.50")
    service2, _ = resolver(tmp_path / "override", {"show version": "Cisco IOS Software, Version 15.2\nx uptime is 1 day\nWS-C3750X", "show inventory": "SN: X"})
    assert service2.resolve(object(), management_ip="192.0.2.51", platform_override="cisco_ios").platform == "cisco_ios"


def test_snapshot_has_only_inventory_facts(tmp_path):
    outputs = {"show version": "Cisco IOS Software, Version 15.2\nx uptime is 1 day\nWS-C3750X", "show inventory": "SN: X"}
    service, _ = resolver(tmp_path, outputs)
    service.resolve(object(), management_ip="192.0.2.60")
    raw = json.loads((tmp_path / "inventory.json").read_text())
    text = json.dumps(raw)
    assert "password" not in text.casefold()
    assert not ({"interfaces", "vlans", "credentials"} & set(next(iter(raw["devices"].values()))))
