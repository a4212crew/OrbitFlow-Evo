"""Validated external policy contract; providers can load JSON, database or API data."""

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Protocol


@dataclass(frozen=True)
class ServiceIdentity:
    field: str
    value: str


@dataclass(frozen=True)
class ServicePolicy:
    platform: str
    database_rule: str
    interface_rule: str
    signature: tuple[tuple[ServiceIdentity, ...], ...]
    required: tuple[tuple[ServiceIdentity, ...], ...]
    baseline_complete: bool


@dataclass(frozen=True)
class VlanPolicy:
    policy_id: str
    database_rule: str
    object_types: tuple[str, ...]
    required_domains: tuple[str, ...]
    interface_rule: str
    match_all: tuple[int, ...]
    match_any: tuple[int, ...]
    required_vlans: tuple[int, ...]
    service_rules: tuple[ServicePolicy, ...] = ()


class PolicyProvider(Protocol):
    def load(self) -> VlanPolicy: ...


@dataclass(frozen=True)
class JsonPolicyProvider:
    path: str | Path

    def load(self) -> VlanPolicy:
        try:
            data = json.loads(Path(self.path).read_text(encoding="utf-8"),
                              object_pairs_hook=_unique_keys)
        except (ValueError, UnicodeError):
            raise ValueError("Invalid compliance policy JSON") from None
        return parse_policy(data)


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate policy key")
        result[key] = value
    return result


def _fields(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError("Invalid compliance policy fields")


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,128}", value):
        raise ValueError("Invalid policy identifier")
    return value


def _values(values, *, domains=False):
    if not isinstance(values, list) or not values:
        raise ValueError("Policy requires a nonempty list")
    result = set()
    for value in values:
        if type(value) is int:
            first = last = value
        elif isinstance(value, str) and re.fullmatch(r"[0-9]+(?:-[0-9]+)?", value):
            parts = value.split("-")
            first, last = int(parts[0]), int(parts[-1])
        elif domains and isinstance(value, str) and re.search(r"[A-Za-z_]", value):
            result.add(_identifier(value))
            continue
        else:
            raise ValueError("Invalid policy VLAN or domain")
        if not 1 <= first <= last <= 4094:
            raise ValueError("Policy VLAN range must be within 1-4094")
        if first == 1:
            raise ValueError("VLAN 1 is omitted by observation and cannot be assessed")
        result.update(str(v) if domains else v for v in range(first, last + 1))
    return tuple(sorted(result))


def parse_policy(data) -> VlanPolicy:
    """Reject typos/unknown fields before a run; never echo arbitrary input values."""
    fields = ("schema_version", "policy_id", "database", "interface")
    _fields(data, (*fields, "service_rules") if isinstance(data, dict) and "service_rules" in data else fields)
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("Unsupported compliance policy version")
    database, interface = data["database"], data["interface"]
    _fields(database, ("rule_id", "object_types", "required_domains"))
    _fields(interface, ("rule_id", "match_all", "match_any", "required_vlans"))
    types = database["object_types"]
    if (not isinstance(types, list) or not types
            or any(t not in ("vlan", "bridge_domain", "vsi") for t in types)):
        raise ValueError("Invalid policy object types")
    database_rule, interface_rule = _identifier(database["rule_id"]), _identifier(interface["rule_id"])
    if database_rule == interface_rule:
        raise ValueError("Policy rule IDs must be distinct")
    services = []
    rule_ids = {database_rule, interface_rule}
    platforms = set()
    entries = data.get("service_rules", [])
    if not isinstance(entries, list):
        raise ValueError("Invalid service rules")
    for entry in entries:
        _fields(entry, ("platform", "database_rule", "interface_rule", "signature", "required", "baseline_complete"))
        platform = _identifier(entry["platform"])
        if platform != "cisco_xr" or platform in platforms:
            raise ValueError("Unsupported or duplicate service platform")
        platforms.add(platform)
        ids = [_identifier(entry[field]) for field in ("database_rule", "interface_rule")]
        if len(set(ids)) != 2 or rule_ids.intersection(ids):
            raise ValueError("Policy rule IDs must be distinct")
        rule_ids.update(ids)
        if type(entry["baseline_complete"]) is not bool:
            raise ValueError("Invalid service baseline completeness")
        services.append(ServicePolicy(platform, *ids, _identity_groups(entry["signature"]),
                                      _identity_groups(entry["required"]), entry["baseline_complete"]))
    return VlanPolicy(
        _identifier(data["policy_id"]), database_rule, tuple(sorted(set(types))),
        _values(database["required_domains"], domains=True), interface_rule,
        _values(interface["match_all"]), _values(interface["match_any"]),
        _values(interface["required_vlans"]),
        tuple(services),
    )


def _identity_groups(groups):
    """AND across groups, OR across exact typed identities within each group."""
    if not isinstance(groups, list) or not groups:
        raise ValueError("Service identities require nonempty groups")
    result = []
    for group in groups:
        if not isinstance(group, list) or not group:
            raise ValueError("Service identities require nonempty alternatives")
        alternatives = []
        for selector in group:
            _fields(selector, ("field", "value"))
            if selector["field"] not in ("object_id", "domain_id"):
                raise ValueError("Invalid service identity field")
            alternatives.append(ServiceIdentity(selector["field"], _identifier(selector["value"])))
        result.append(tuple(sorted(set(alternatives), key=lambda item: (item.field, item.value))))
    return tuple(result)
