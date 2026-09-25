"""Minimal single-device live validation for the interface capability.

This integration utility intentionally leaves configuration and secret retrieval to
the caller. Inventory resolution precedes collection on the same session.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from orbitflow.inventory import DeviceInventoryResolver, JsonInventoryStore
from orbitflow.capabilities import InterfaceService
from orbitflow.models import InterfaceRecord
from orbitflow.transport import (
    DeviceCredentials,
    DeviceSession,
    TransportConfig,
    connect_device,
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
) -> list[InterfaceRecord]:
    """Resolve then collect; pass platform=None for automatic detection.

    device_name is retained as an empty-result display fallback only.
    """
    resolver = DeviceInventoryResolver(JsonInventoryStore(inventory_path))
    session: DeviceSession
    with connect_device(device_host, credentials, transport_config) as session:
        context = resolver.resolve(
            session, management_ip=device_host, platform_override=platform
        )
        records = InterfaceService().collect(
            session,
            context=context,
        )

    display_name = records[0].device_name if records else (device_name or device_host)
    print(
        f"{display_name} ({context.management_ip}, {context.platform}): {len(records)} interface(s)",
        file=output,
    )
    for record in records:
        description = record.port_description or "-"
        admin_status = record.admin_status or "unknown"
        oper_status = record.oper_status or "unknown"
        print(
            f"  {record.port_name}: admin={admin_status}, oper={oper_status}, "
            f"description={description}",
            file=output,
        )
    return records
