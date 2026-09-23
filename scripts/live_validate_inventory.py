"""Minimal single-device live validation for inventory identification.

This operator utility exercises the existing transport, resolver, and latest
JSON inventory store.  It intentionally supplies no platform override so that
automatic platform and device-family detection are part of the validation.
"""

from __future__ import annotations

import getpass
import platform as host_platform
import sys
from datetime import datetime
from pathlib import Path
from typing import TextIO

from orbitflow.inventory import DeviceInventoryResolver, JsonInventoryStore
from orbitflow.models import DeviceContext
from orbitflow.transport import DeviceCredentials, TransportConfig, connect_device

# Deliberately grouped here so an operator can replace the validation target
# and non-secret Teleport routing values without changing the reusable runner.
DEVICE_HOST = "10.251.10.98"
DEVICE_USERNAME = "lightningadmin"
TELEPORT_PROXY = "teleport.lynhamnetworks.au:443"
TELEPORT_CLUSTER = "lynhamcluster"
BASTION_HOST = "bastion-lyn-dc1-vic"
BASTION_USER = "lightningadmin"
INVENTORY_PATH = Path("data/live_validation/inventory.json")


def _linux_teleport_identity_paths() -> tuple[Path | None, Path | None]:
    """Return conventional active-profile identity paths on Linux."""
    if host_platform.system().lower() != "linux":
        return None, None
    proxy_host = TELEPORT_PROXY.rsplit(":", 1)[0]
    key_path = Path.home() / ".tsh" / "keys" / proxy_host / BASTION_USER
    return key_path, key_path.with_name(f"{key_path.name}-cert.pub")


def _format_value(value: object) -> str:
    """Render normalized values consistently for manual validation."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return ", ".join(str(item) for item in value) or "[]"
    if value is None or value == "":
        return "-"
    return str(value)


def _print_context(
    context: DeviceContext, events: tuple[str, ...], *, output: TextIO
) -> None:
    """Print every normalized inventory field and reconciliation event."""
    field_names = (
        "device_id",
        "management_ip",
        "observed_management_ips",
        "hostname",
        "vendor",
        "platform",
        "device_family",
        "hardware_model",
        "capability_profile",
        "capability_flags",
        "serial_number",
        "software_version",
        "uptime",
        "collection_status",
        "last_successful_collection",
        "last_collection_attempt",
        "collection_error",
    )
    print("Normalized DeviceContext:", file=output)
    for field_name in field_names:
        print(
            f"{field_name}: {_format_value(getattr(context, field_name))}", file=output
        )
    print(f"reconciliation_events: {_format_value(events)}", file=output)


def _print_inventory_state(
    label: str, contexts: tuple[DeviceContext, ...], *, output: TextIO
) -> None:
    """Print identity-focused inventory state for before/after comparison."""
    print(f"{label} inventory state:", file=output)
    print(f"total_stored_device_count: {len(contexts)}", file=output)
    if not contexts:
        print("devices: []", file=output)
        return
    for index, context in enumerate(contexts, start=1):
        print(f"device[{index}]:", file=output)
        for field_name in (
            "device_id",
            "serial_number",
            "management_ip",
            "observed_management_ips",
        ):
            print(
                f"  {field_name}: {_format_value(getattr(context, field_name))}",
                file=output,
            )


def run_live_validation(
    device_host: str,
    credentials: DeviceCredentials,
    transport_config: TransportConfig,
    *,
    inventory_path: str | Path = INVENTORY_PATH,
    output: TextIO = sys.stdout,
) -> DeviceContext:
    """Identify one live device, persist its snapshot, and print its context."""
    store = JsonInventoryStore(inventory_path)
    resolver = DeviceInventoryResolver(store)
    _print_inventory_state("Before", store.contexts(), output=output)
    with connect_device(device_host, credentials, transport_config) as session:
        context = resolver.resolve(session, management_ip=device_host)

    _print_context(context, resolver.last_events, output=output)
    _print_inventory_state("After", store.contexts(), output=output)
    print(f"snapshot_path: {inventory_path}", file=output)
    return context


def main() -> None:
    """Prompt only for the target password and validate the configured target."""
    password = getpass.getpass("Device password: ")
    key_path, cert_path = _linux_teleport_identity_paths()
    run_live_validation(
        DEVICE_HOST,
        DeviceCredentials(username=DEVICE_USERNAME, password=password),
        TransportConfig(
            proxy=TELEPORT_PROXY,
            cluster=TELEPORT_CLUSTER,
            bastion_host=BASTION_HOST,
            bastion_user=BASTION_USER,
            teleport_key_path=key_path,
            teleport_cert_path=cert_path,
        ),
    )


if __name__ == "__main__":
    main()
