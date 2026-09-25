"""Minimal single-device live validation for the VLAN capability.

This operator utility is intentionally limited to collecting and displaying the
existing normalized VLAN state. Inventory resolution precedes collection on the same session.
"""

from __future__ import annotations

import getpass
import platform as host_platform
import sys
from dataclasses import fields
from pathlib import Path
from typing import TextIO

from orbitflow.inventory import DeviceInventoryResolver, JsonInventoryStore
from orbitflow.capabilities import VlanService
from orbitflow.models import InterfaceVlanObservation, VlanState
from orbitflow.transport import (
    DeviceCredentials,
    DeviceSession,
    TransportConfig,
    connect_device,
)

SUPPORTED_PLATFORMS = (
    "cisco_ios",
    "cisco_xe",
    "cisco_xr",
    "huawei_vrp",
    "ubiquiti_edgeswitch",
)

# Deliberately grouped here so the single-device validation target remains easy
# to replace without changing the reusable validation function below.
DEVICE_HOST = "10.251.10.98"
DEVICE_PLATFORM = "cisco_xr"
DEVICE_USERNAME = "lightningadmin"
TELEPORT_PROXY = "teleport.lynhamnetworks.au:443"
TELEPORT_CLUSTER = "lynhamcluster"
BASTION_HOST = "bastion-lyn-dc1-vic"
BASTION_USER = "lightningadmin"


def _linux_teleport_identity_paths() -> tuple[Path | None, Path | None]:
    """Return conventional active-profile identity paths on Linux."""
    if host_platform.system().lower() != "linux":
        return None, None
    proxy_host = TELEPORT_PROXY.rsplit(":", 1)[0]
    key_path = Path.home() / ".tsh" / "keys" / proxy_host / BASTION_USER
    return key_path, key_path.with_name(f"{key_path.name}-cert.pub")


def _format_value(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, tuple):
        return ",".join(str(item) for item in value) or "[]"
    if value == "":
        return "-"
    return str(value)


def _format_observation(observation: InterfaceVlanObservation) -> str:
    details = ", ".join(
        f"{field.name}={_format_value(getattr(observation, field.name))}"
        for field in fields(observation)
        if field.name not in {"interface_name", "description"}
    )
    return (
        f"  {observation.interface_name}: "
        f"description={_format_value(observation.description)}, {details}"
    )


def run_live_validation(
    device_host: str,
    platform: str | None,
    credentials: DeviceCredentials,
    transport_config: TransportConfig,
    *,
    device_name: str | None = None,
    inventory_path: str | Path = Path("data/live_validation/inventory.json"),
    output: TextIO = sys.stdout,
) -> VlanState:
    """Resolve then collect; pass platform=None for automatic detection.

    device_name is retained for call compatibility; observed identity is used.
    """
    resolver = DeviceInventoryResolver(JsonInventoryStore(inventory_path))
    session: DeviceSession
    with connect_device(device_host, credentials, transport_config) as session:
        context = resolver.resolve(
            session, management_ip=device_host, platform_override=platform
        )
        state = VlanService().collect(
            session,
            context=context,
        )

    print(f"Device: {state.device_name or device_host}", file=output)
    print(f"Address: {state.device_ip}", file=output)
    print(f"Platform: {state.platform}", file=output)
    print(f"Collected: {state.collection_time.isoformat()}", file=output)
    print(f"\nVLAN/service objects ({len(state.objects)}):", file=output)
    if not state.objects:
        print("  (none observed)", file=output)
    for item in state.objects:
        print(
            f"  type={item.object_type}, id={item.object_id}, "
            f"name={_format_value(item.name)}, vlan_ids={_format_value(item.vlan_ids)}",
            file=output,
        )

    print(f"\nInterface VLAN observations ({len(state.interfaces)}):", file=output)
    if not state.interfaces:
        print("  (none observed)", file=output)
    for observation in state.interfaces:
        print(_format_observation(observation), file=output)
    return state


def main() -> None:
    """Prompt only for the target password and validate the configured target."""
    password = getpass.getpass("Device password: ")
    key_path, cert_path = _linux_teleport_identity_paths()

    run_live_validation(
        DEVICE_HOST,
        DEVICE_PLATFORM,
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
