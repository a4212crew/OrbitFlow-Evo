"""Atomic latest-known JSON storage and conservative identity reconciliation."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
from typing import Callable
from uuid import uuid4

from orbitflow.models import DeviceContext


class JsonInventoryStore:
    """Keep only latest stable facts, plus the latest collection outcome."""

    def __init__(self, path: str | Path, *, id_factory: Callable[[], str] | None = None) -> None:
        self.path = Path(path)
        self._id_factory = id_factory or (lambda: str(uuid4()))

    def reconcile(self, observed: DeviceContext) -> tuple[DeviceContext, tuple[str, ...]]:
        data = self._read()
        devices: dict[str, dict[str, object]] = data["devices"]
        events: list[str] = []
        serial_key = _serial_key(observed.vendor, observed.serial_number)
        matches = [item for item in devices.values() if serial_key and _serial_key(str(item.get("vendor", "")), str(item.get("serial_number", ""))) == serial_key]
        prior_at_ip = [item for item in devices.values() if observed.management_ip in item.get("observed_management_ips", [])]

        # Enrich only one serial-less identity observed at this exact address.
        # Hostname and model are deliberately not physical identity evidence.
        serial_discovery_match = (
            prior_at_ip[0]
            if observed.serial_number
            and len(prior_at_ip) == 1
            and not str(prior_at_ip[0].get("serial_number", "")).strip()
            else None
        )

        if matches:
            previous = matches[0]
            device_id = str(previous["device_id"])
            ips = tuple(dict.fromkeys((*previous.get("observed_management_ips", []), observed.management_ip)))
            if observed.management_ip not in previous.get("observed_management_ips", []):
                events.append("management_ip_changed")
        elif serial_discovery_match:
            previous = serial_discovery_match
            device_id = str(previous["device_id"])
            ips = tuple(dict.fromkeys((*previous.get("observed_management_ips", []), observed.management_ip)))
            events.append("serial_number_discovered")
        else:
            device_id = self._id_factory()
            ips = (observed.management_ip,)
            if prior_at_ip and observed.serial_number and any(
                item.get("serial_number") and item.get("serial_number") != observed.serial_number
                for item in prior_at_ip
            ):
                events.append("likely_replacement_or_ip_reassignment")
            if observed.serial_number and any(
                item.get("hostname") == observed.hostname and item.get("serial_number") != observed.serial_number
                for item in devices.values()
            ):
                events.append("hostname_collision")

        context = replace(observed, device_id=device_id, observed_management_ips=ips)
        devices[device_id] = _serialize(context)
        data["last_events"] = events
        self._write(data)
        return context, tuple(events)

    def record_failure(self, management_ip: str, attempted_at: datetime, error: str) -> None:
        data = self._read()
        matched = False
        for device_id, raw in data["devices"].items():
            if management_ip in raw.get("observed_management_ips", []):
                # Only attempt metadata changes: successful stable facts remain intact.
                raw["last_collection_attempt"] = attempted_at.isoformat()
                raw["collection_status"] = "failed"
                raw["collection_error"] = error
                data["devices"][device_id] = raw
                matched = True
        data["last_events"] = ["collection_failed"] if matched else ["unresolved_collection_failed"]
        self._write(data)

    def contexts(self) -> tuple[DeviceContext, ...]:
        return tuple(_deserialize(raw) for raw in self._read()["devices"].values())

    def _read(self) -> dict[str, object]:
        if not self.path.exists():
            return {"schema_version": 1, "devices": {}, "last_events": []}
        with self.path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        if data.get("schema_version") != 1 or not isinstance(data.get("devices"), dict):
            raise ValueError("unsupported or invalid inventory snapshot")
        return data

    def _write(self, data: dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, self.path)


def _serial_key(vendor: str, serial: str) -> str:
    return f"{vendor.strip().casefold()}:{serial.strip().casefold()}" if serial.strip() else ""


def _serialize(context: DeviceContext) -> dict[str, object]:
    raw = asdict(context)
    raw["observed_management_ips"] = list(context.observed_management_ips)
    raw["capability_flags"] = list(context.capability_flags)
    raw["last_successful_collection"] = context.last_successful_collection.isoformat()
    raw["last_collection_attempt"] = context.last_collection_attempt.isoformat()
    return raw


def _deserialize(raw: dict[str, object]) -> DeviceContext:
    values = dict(raw)
    values["observed_management_ips"] = tuple(values["observed_management_ips"])
    values["capability_flags"] = tuple(values["capability_flags"])
    values["last_successful_collection"] = datetime.fromisoformat(str(values["last_successful_collection"]))
    values["last_collection_attempt"] = datetime.fromisoformat(str(values["last_collection_attempt"]))
    return DeviceContext(**values)  # type: ignore[arg-type]
