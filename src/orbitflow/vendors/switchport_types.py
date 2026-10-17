"""Serializable switchport observations; unknown and empty are distinct."""
from dataclasses import dataclass, asdict
import re
from orbitflow.vendors.vlan_types import parse_vlan_list


@dataclass(frozen=True)
class SwitchportObservation:
    fields: dict
    facts: dict
    evidence: str

    def to_dict(self):
        return asdict(self)


def labeled(text):
    fields, key = {}, None
    for line in text.splitlines():
        if ':' in line:
            key, value = line.strip().split(':', 1)
            # Duplicate labels are ambiguous, never silently last-wins.
            if key in fields:
                raise ValueError('duplicate switchport field')
            fields[key] = value.strip()
        elif key and line.strip() and (line[:1].isspace() or re.fullmatch(r'[\s\d,\-]+', line)):
            fields[key] += ' ' + line.strip()
        else:
            key = None
    return fields


def vlan(value):
    match = re.fullmatch(r'(\d+)(?:\s+\(.*\))?', value or '')
    return int(match[1]) if match and 1 <= int(match[1]) <= 4094 else None


def vlans(value):
    if value is None:
        return None
    if value.upper() in {'ALL', 'NONE'}:
        return value.upper()
    try:
        return list(parse_vlan_list(value))
    except ValueError:
        return None
