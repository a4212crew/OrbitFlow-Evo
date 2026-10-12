"""Reusable read-only VLAN observation capability."""

from datetime import datetime, timezone
from typing import Callable, Protocol

from orbitflow.models import DeviceContext, VlanState
from orbitflow.transport import DeviceSession
from orbitflow.vendors.common import DeviceCLI
from orbitflow.vendors.vlan_types import VlanCollection
from orbitflow.vendors.cisco.vlans import (
    CiscoVlanAdapter,
    CiscoASRVlanAdapter,
    CiscoXEVlanAdapter,
    CiscoXRVlanAdapter,
)
from orbitflow.vendors.huawei.vlans import HuaweiVlanAdapter
from orbitflow.vendors.ubiquiti.vlans import EdgeSwitchVlanAdapter


class VlanCapabilityError(Exception):
    """A platform cannot provide a trustworthy VLAN observation."""


class _Adapter(Protocol):
    def __init__(self, session: DeviceSession, *, timeout: float = 10.0, cli: DeviceCLI | None = None) -> None: ...
    def collect(self) -> VlanCollection: ...


_ADAPTERS: dict[str, type[_Adapter]] = {
    "cisco_ios": CiscoVlanAdapter,
    "cisco_xe": CiscoXEVlanAdapter,
    "cisco_xr": CiscoXRVlanAdapter,
    "huawei_vrp": HuaweiVlanAdapter,
    "ubiquiti_edgeswitch": EdgeSwitchVlanAdapter,
}


class VlanService:
    """Collect configured VLAN facts through an established device session."""

    def __init__(
        self, clock: Callable[[], datetime] | None = None, *, timeout: float = 10.0
    ) -> None:
        self._clock, self._timeout = (
            clock or (lambda: datetime.now(timezone.utc)),
            timeout,
        )

    def lookup(self, session, context, vlan_id, *, cli=None):
        """Read-only operational lookup on approved Catalyst families."""
        if (context.platform not in {"cisco_ios", "cisco_xe"}
                or context.device_family not in {"C3750X", "C3850"}
                or type(vlan_id) is not int or not 1 <= vlan_id <= 4094):
            raise VlanCapabilityError("unsupported VLAN lookup")
        return CiscoVlanAdapter(session, timeout=self._timeout, cli=cli).lookup(vlan_id)

    def collect(
        self,
        session: DeviceSession,
        context: DeviceContext | None = None,
        *,
        cli: DeviceCLI | None = None,
        device_ip: str | None = None,
        platform: str | None = None,
        device_name: str | None = None,
        preserve_full_evidence: bool = False,
    ) -> VlanState:
        """Collect with resolved context (preferred) or legacy identity keywords.

        No discovery is performed and the caller retains session ownership.
        A supplied ``cli`` is borrowed without closing it. Without one, the
        selected adapter owns a temporary shell for this operation.
        """
        # Context is authoritative; reject ambiguous mixed calling conventions.
        if context is not None:
            if device_ip is not None or platform is not None or device_name is not None:
                raise VlanCapabilityError("context cannot be combined with legacy identity arguments")
            device_ip, platform, device_name = (
                context.management_ip, context.platform, context.hostname
            )
        elif device_ip is None or platform is None:
            raise VlanCapabilityError("provide context or device_ip and platform")
        adapter = _ADAPTERS.get(platform)
        # EVC is a device capability, not an OS identifier. Reuse the existing
        # EVC adapter without relabelling IOS devices as IOS-XE.
        if context is not None and platform in {"cisco_ios", "cisco_xe"}:
            if ("evc" in context.capability_flags
                    or context.capability_profile in {"me3600x_evc", "asr920_evc"}
                    or context.device_family in {"ME3600X", "ASR920"}):
                adapter = CiscoXEVlanAdapter
            if context.device_family == "ASR920" or context.capability_profile == "asr920_evc":
                adapter = CiscoASRVlanAdapter
        if adapter is None:
            raise VlanCapabilityError(f"unsupported VLAN platform: {platform}")
        try:
            options = {}
            if preserve_full_evidence:
                if context is None or context.device_family not in {"C3750X", "C3850"}:
                    raise VlanCapabilityError("full evidence requires approved Catalyst context")
                options["preserve_full_evidence"] = True
            result = adapter(session, timeout=self._timeout, cli=cli, **options).collect()
        except Exception as exc:
            raise VlanCapabilityError(
                f"VLAN collection failed for {device_name or device_ip} ({device_ip}, {platform}): {exc}"
            ) from exc
        return VlanState(
            device_name or result.device_name,
            device_ip,
            platform,
            result.interfaces,
            result.objects,
            self._clock(),
            result.configuration,
        )
