"""Version-one closed-schema, immutable, deterministic change plans."""

from dataclasses import dataclass, field
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re

from orbitflow.logging import sanitize_text
from orbitflow.models import DeviceContext
from orbitflow.vendors.cisco.change_plan import render_vlan


class PlanError(ValueError):
    """Fixed diagnostic messages intentionally exclude untrusted input."""


def require(condition, message):
    if not condition:
        raise PlanError(message)


def keys(value, expected):
    require(type(value) is dict and set(value) == set(expected.split()), "invalid schema fields")


def safe_text(value):
    require(type(value) is str and 0 < len(value) <= 256, "invalid text field")
    require(value == value.strip() and all(32 <= ord(c) < 127 for c in value), "unsafe text field")
    require(sanitize_text(value) == value and not re.search(
        r"(?i)password|passwd|secret|token|credential|private.key|authorization|\botp\b|snmp.community|://|-----BEGIN", value
    ), "secret-bearing text is forbidden")


def label(value):
    safe_text(value)
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value) is not None, "invalid identifier")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def decode(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate JSON field")
            result[key] = value
        return result
    try:
        return json.loads(text, object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(PlanError("invalid JSON number")))
    except (ValueError, TypeError, RecursionError):
        raise PlanError("invalid plan JSON") from None


IDENTITY_FIELDS = "inventory_id management_ip hostname platform device_family capability_profile serial_number"
POLICY = dict(dry_run=True, require_approval=True, backup_required=True, save_after_verify=True,
              max_concurrent_devices=1, max_devices_per_run=5, stop_after_failures=1,
              recovery_strategy="manual", rollback_available=False, unknown_outcome="stop_and_escalate")


def identity(context: DeviceContext):
    return dict(inventory_id=context.device_id, management_ip=str(ipaddress.ip_address(context.management_ip)),
                hostname=context.hostname, platform=context.platform, device_family=context.device_family,
                capability_profile=context.capability_profile, serial_number=context.serial_number)


def validate_operation(op, target):
    keys(op, "kind vlan_id vlan_name precondition verification commands")
    require(op["kind"] == "ensure_vlan_present", "unsupported operation")
    require(type(op["vlan_id"]) is int and 2 <= op["vlan_id"] <= 4094 and
            op["vlan_id"] not in range(1002, 1006), "invalid or reserved VLAN")
    label(op["vlan_name"])
    require(len(op["vlan_name"]) <= 32, "invalid VLAN name")
    keys(op["precondition"], "present name")
    keys(op["verification"], "present name")
    pre, post = op["precondition"], op["verification"]
    require(type(pre["present"]) is bool and type(post["present"]) is bool, "invalid fact type")
    require(pre == {"present": False, "name": ""} or
            pre == {"present": True, "name": op["vlan_name"]}, "conflicting existing VLAN state")
    require(post == {"present": True, "name": op["vlan_name"]}, "required verification missing")
    try:
        commands = render_vlan(target, op["vlan_id"], op["vlan_name"], already_correct=pre["present"])
    except ValueError:
        raise PlanError("unsupported configuration profile") from None
    require(type(op["commands"]) is list and op["commands"] == commands, "unsupported or tampered commands")


def validate(data):
    if type(data) is dict and type(data.get("schema_version")) is int and data["schema_version"] == 2:
        from .guided_schema import validate as validate_guided
        validate_guided(data)
        return
    keys(data, "schema_version change_id source intent targets execution_policy")
    require(type(data["schema_version"]) is int and data["schema_version"] == 1, "unsupported schema version")
    label(data["change_id"])
    safe_text(data["intent"])
    keys(data["source"], "kind reference version")
    require(data["source"]["kind"] in ("manual", "spreadsheet", "template", "compliance"), "unsupported source")
    label(data["source"]["reference"])
    label(data["source"]["version"])
    policy = data["execution_policy"]
    keys(policy, " ".join(POLICY))
    for key, default in POLICY.items():
        require(type(policy[key]) is type(default), "invalid policy type")
        if type(default) is int:
            require(1 <= policy[key] <= 100, "unsafe execution limit")
        else:
            require(policy[key] == default, "unsupported safety policy")
    require(policy["max_concurrent_devices"] <= policy["max_devices_per_run"], "invalid execution limits")
    targets = data["targets"]
    require(type(targets) is list and 0 < len(targets) <= policy["max_devices_per_run"], "invalid target count")
    seen = {key: set() for key in ("inventory_id", "management_ip", "hostname", "serial_number")}
    for target in targets:
        keys(target, "identity operations verification_capability")
        require(target["verification_capability"] == "vlan_database", "missing verification capability")
        ident = target["identity"]
        keys(ident, IDENTITY_FIELDS)
        for key, value in ident.items():
            if key == "serial_number" and value == "":
                continue
            if key == "management_ip":
                safe_text(value)
            else:
                label(value)
        try:
            require(str(ipaddress.ip_address(ident["management_ip"])) == ident["management_ip"], "noncanonical IP")
        except ValueError:
            raise PlanError("invalid management IP") from None
        for key in seen:
            value = ident[key].casefold()
            if value:
                require(value not in seen[key], "duplicate or ambiguous target")
                seen[key].add(value)
        operations = target["operations"]
        require(type(operations) is list and 0 < len(operations) <= 100, "invalid operation count")
        vlans = set()
        for op in operations:
            validate_operation(op, ident)
            require(op["vlan_id"] not in vlans, "duplicate or conflicting operation")
            vlans.add(op["vlan_id"])


@dataclass(frozen=True)
class ChangePlan:
    """Canonical content only: callers receive copies, never mutable plan internals."""

    content: str = field(repr=False)

    def __post_init__(self):
        data = decode(self.content)
        validate(data)
        object.__setattr__(self, "content", canonical(data))

    @property
    def digest(self):
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()

    def to_dict(self):
        return decode(self.content)

    def preview(self):
        return json.dumps({"digest": self.digest, "plan": self.to_dict()}, indent=2, sort_keys=True)


def create_plan(request, contexts):
    """Resolve IDs against existing DeviceContexts; never refresh inventory or connect."""
    request = decode(canonical(request))
    keys(request, "schema_version change_id source intent targets execution_policy")
    keys(request["source"], "kind reference version")
    require(type(request["targets"]) is list, "invalid targets")
    contexts = tuple(contexts)
    resolved = []
    for target in request["targets"]:
        keys(target, "inventory_id expected_hostname expected_platform operations")
        matches = [c for c in contexts if c.device_id == target["inventory_id"]]
        require(len(matches) == 1, "unresolved or ambiguous inventory identity")
        context = matches[0]
        require(context.collection_status == "success", "inventory observation unavailable")
        require(context.hostname == target["expected_hostname"] and context.platform == target["expected_platform"],
                "inventory identity mismatch")
        ident = identity(context)
        # Reject collisions even if only one of the ambiguous records was requested.
        for other in contexts:
            if other is context:
                continue
            require(not (other.hostname.casefold() == context.hostname.casefold() or
                         context.management_ip in (other.management_ip, *other.observed_management_ips) or
                         (context.serial_number and context.serial_number == other.serial_number)),
                    "ambiguous inventory identity")
        require(type(target["operations"]) is list, "invalid operations")
        operations = []
        for op in target["operations"]:
            # Manual callers must supply the exact allowlisted commands for review.
            supplied = "commands" in op if type(op) is dict else False
            keys(op, "kind vlan_id vlan_name precondition verification" + (" commands" if supplied else ""))
            require(request["source"]["kind"] != "manual" or supplied, "manual commands required")
            if not supplied:
                try:
                    op["commands"] = render_vlan(ident, op["vlan_id"], op["vlan_name"],
                                                 already_correct=op["precondition"]["present"] is True)
                except (ValueError, KeyError, TypeError):
                    raise PlanError("invalid operation or unsupported profile") from None
            operations.append(op)
        resolved.append(dict(identity=ident, operations=operations, verification_capability="vlan_database"))
    request["targets"] = resolved
    return ChangePlan(canonical(request))


def save_plan(plan, path):
    """Exclusive creation prevents accidental replacement of a reviewed artifact."""
    checked = ChangePlan(plan.content)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(checked.preview() + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def load_plan(path):
    data = decode(Path(path).read_text(encoding="utf-8"))
    keys(data, "digest plan")
    plan = ChangePlan(canonical(data["plan"]))
    require(data["digest"] == plan.digest, "plan digest mismatch")
    return plan
