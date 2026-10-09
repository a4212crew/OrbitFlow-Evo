"""Normalized models shared by device capabilities and their consumers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class InterfaceRecord:
    """Vendor-neutral interface description and state observation."""

    device_name: str
    device_ip: str
    platform: str
    port_name: str
    port_description: str
    admin_status: str
    oper_status: str
    collection_time: datetime


@dataclass(frozen=True)
class VlanObject:
    """A configured VLAN or vendor service object (identities are not conflated)."""

    object_type: str
    object_id: str
    name: str = ""
    vlan_ids: tuple[int, ...] = ()
    domain_id: str = ""

    def __post_init__(self):
        object.__setattr__(self, "object_type", self.object_type.replace("-", "_"))
        domain = self.domain_id or self.object_id
        object.__setattr__(self, "domain_id", domain)
        object.__setattr__(self, "name", self.name or domain)


@dataclass(frozen=True)
class InterfaceVlanObservation:
    """One normalized interface forwarding profile, with supporting vendor facts.

    ``tagged_vlans`` is an explicit outer VLAN tuple, ``ALL``, ``NONE``, or
    an empty tuple (not applicable). Domain IDs are strings because forwarding
    domains may be named. ``service_details`` retains individual EVC observations
    including inner-tag facts; consumers use the top-level normalized fields.
    """

    interface_name: str
    description: str = ""
    mode: str = "unknown"
    access_vlan: Optional[int] = None
    native_vlan: Optional[int] = None
    pvid: Optional[int] = None
    allowed_vlans: Optional[tuple[int, ...]] = None
    tagged_vlans: tuple[int, ...] | str = ()
    untagged_vlans: tuple[int, ...] = ()
    excluded_vlans: tuple[int, ...] = ()
    service_vlan: Optional[int] = None
    control_vlan: Optional[int] = None
    outer_vlan: Optional[int] = None
    inner_vlan: Optional[int] = None
    referenced_vlans: tuple[int, ...] = ()
    vlan_source: str = ""
    vlan_database_applicable: bool = True
    service_binding_type: str = ""
    service_binding_name: str = ""
    port_type: str = ""
    untagged_vlan: str = ""
    bridge_domains: tuple[str, ...] = ()
    service_mappings: tuple[str, ...] = ()
    service_details: tuple[InterfaceVlanObservation, ...] = ()


@dataclass(frozen=True)
class VlanState:
    """Vendor-neutral snapshot returned by :class:`VlanService`."""

    device_name: str
    device_ip: str
    platform: str
    interfaces: tuple[InterfaceVlanObservation, ...]
    objects: tuple[VlanObject, ...]
    collection_time: datetime
    configuration: tuple[ConfigFact, ...] | None = None


@dataclass(frozen=True)
class TagRewrite:
    """Observed syntax only; does not assert hardware or template eligibility.

    tag_count is the removed count for pop, added count for push, and input
    count for translate. output_tags retains the ordered replacement stack.
    """

    direction: str
    operation: str
    tag_count: int
    symmetric: bool
    parameters: str
    output_tags: tuple[tuple[str, int], ...] = ()
    translation: str = ""


@dataclass(frozen=True)
class ConfigFact:
    """Allowlisted saved-configuration fact with exact, sanitized source evidence.

    The vendor observation layer owns syntax, ordering and nesting. References
    remain references; they never manufacture configured interface identities.
    """

    kind: str
    value: str | tuple[int, ...] | TagRewrite
    source_filename: str
    line: int
    excerpt: str
    children: tuple[ConfigFact, ...] = ()


@dataclass(frozen=True)
class DeviceContext:
    """Latest observed stable identity and capability-selection context."""

    device_id: str
    management_ip: str
    observed_management_ips: tuple[str, ...]
    hostname: str
    vendor: str
    platform: str
    device_family: str
    hardware_model: str
    capability_profile: str
    capability_flags: tuple[str, ...]
    serial_number: str
    software_version: str
    uptime: str
    last_successful_collection: datetime
    last_collection_attempt: datetime
    collection_status: str = "success"
    collection_error: str = ""
