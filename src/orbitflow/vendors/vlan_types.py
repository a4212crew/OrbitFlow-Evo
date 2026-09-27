"""Internal result type and VLAN-list parsing shared by vendor adapters."""

from dataclasses import dataclass, replace
import re

from orbitflow.models import InterfaceVlanObservation, VlanObject


@dataclass(frozen=True)
class VlanCollection:
    device_name: str
    interfaces: tuple[InterfaceVlanObservation, ...]
    objects: tuple[VlanObject, ...]


def parse_vlan_list(value: str, *, range_word: str = "-") -> tuple[int, ...]:
    """Expand comma/space separated VLAN IDs and inclusive ranges deterministically."""
    text = value.strip()
    if not text:
        return ()
    if range_word == "to":
        text = re.sub(r"\s+to\s+", "-", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*-\s*", "-", text.replace(",", " "))
    result: set[int] = set()
    for token in text.split():
        match = re.fullmatch(r"(\d+)(?:-(\d+))?", token)
        if not match:
            raise ValueError(f"invalid VLAN list token: {token!r}")
        first = int(match.group(1))
        last = int(match.group(2) or first)
        if not 1 <= first <= 4094 or not 1 <= last <= 4094 or last < first:
            raise ValueError(f"invalid VLAN range: {token!r}")
        result.update(range(first, last + 1))
    return tuple(sorted(result))


def forwarding(
    observation: InterfaceVlanObservation,
    port_type: str,
    *,
    untagged: str | int = "",
    tagged: tuple[int, ...] | str = (),
    domains=(),
    mappings=None,
) -> InterfaceVlanObservation:
    """Build normalized forwarding fields after vendor interpretation."""
    domains = tuple(dict.fromkeys(str(value) for value in domains))
    if mappings is None:
        mappings = [f"untagged -> {untagged}"] if untagged else []
        if tagged == "ALL":
            mappings.append("ALL -> ALL")
        elif isinstance(tagged, tuple):
            mappings.extend(f"{v} -> {v}" for v in tagged)
    # VLAN 1 is intentionally omitted from the normalized reporting contract.
    # Keep supporting vendor facts intact, and preserve ALL/NONE/blank states.
    untagged = "" if str(untagged) == "1" else untagged
    if isinstance(tagged, tuple):
        tagged = tuple(v for v in tagged if v != 1)
    domains = tuple(v for v in domains if v != "1")
    mappings = [m for m in mappings if "1" not in m.split(" -> ")]
    return replace(observation, port_type=port_type, untagged_vlan=str(untagged),
                   tagged_vlans=tagged, bridge_domains=domains,
                   service_mappings=tuple(mappings))


def aggregate_profiles(observations) -> tuple[InterfaceVlanObservation, ...]:
    """Aggregate already normalized services without discarding their relationships."""
    groups = {}
    for item in observations:
        groups.setdefault(item.interface_name, []).append(item)
    result = []
    for items in groups.values():
        if len(items) == 1:
            result.append(items[0])
            continue
        tags = {
            v for item in items if isinstance(item.tagged_vlans, tuple)
            for v in item.tagged_vlans
        }
        if any(i.tagged_vlans == "ALL" for i in items):
            tagged = "ALL"
        elif tags:
            tagged = tuple(sorted(tags))
        elif any(i.tagged_vlans == "NONE" for i in items):
            tagged = "NONE"
        else:
            tagged = ()
        result.append(replace(
            items[0], port_type="evc" if any(i.port_type == "evc" for i in items) else items[0].port_type,
            untagged_vlan=", ".join(dict.fromkeys(i.untagged_vlan for i in items if i.untagged_vlan)),
            tagged_vlans=tagged,
            bridge_domains=tuple(dict.fromkeys(v for i in items for v in i.bridge_domains)),
            service_mappings=tuple(dict.fromkeys(v for i in items for v in i.service_mappings)),
            service_details=tuple(items),
        ))
    return tuple(result)


def visible_objects(objects) -> tuple[VlanObject, ...]:
    """Omit domain 1 without mistaking names containing 1 for VLAN 1."""
    return tuple(obj for obj in objects if obj.domain_id != "1")
