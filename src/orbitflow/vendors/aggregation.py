"""Pure, read-only vendor aggregation relationships; independent of VLAN policy."""
from dataclasses import dataclass
import re
from orbitflow.vendors.interface_names import canonical_interface_name
from orbitflow.vendors.configuration_facts import _safe_source


@dataclass(frozen=True)
class AggregationSnapshot:
    """Device-scoped sanitized stanzas and explicit bindings; empty != unknown."""
    device_id: str
    platform: str
    collection_time: str
    complete: bool
    parents: tuple[str, ...]
    bindings: tuple[tuple[str, str], ...]
    subinterfaces: tuple[tuple[str, str], ...]
    evidence: tuple[tuple[str, str], ...]
    problems: tuple[str, ...]
    device_family: str = ""
    configuration_command: str = ""

    def fields(self, name):
        key = identity(self.platform, name)
        if key in self.parents:
            members = sorted(child for child, parent in self.bindings if parent == key)
            return ['Yes', 'Parent', ', '.join(members) if self.complete else 'Unknown']
        for child, parent in self.bindings:
            if child == key:
                return ['Yes', 'Child', parent]
        return ['', '', '']

    def references(self, name):
        """Parent expands all related stanzas; child expands only base parent."""
        key = identity(self.platform, name)
        selected = {key}
        if key in self.parents:
            selected.update(child for child, parent in self.bindings if parent == key)
            selected.update(child for child, parent in self.subinterfaces if parent == key)
        else:
            selected.update(parent for child, parent in self.bindings if child == key)
        return tuple(name for name, text in self.evidence if name in selected)


def identity(platform, name):
    if platform == 'ubiquiti_edgeswitch':
        match = re.fullmatch(r'lag\s+(\d+)', name.strip(), re.I)
        if match:
            return '3/' + str(int(match[1]))
    return canonical_interface_name(platform, name)


def parent_name(platform, number):
    return identity(platform, {'cisco_xr': 'Bundle-Ether', 'huawei_vrp': 'Eth-Trunk',
                              'ubiquiti_edgeswitch': '3/'}.get(platform, 'Port-channel') + str(int(number)))


def is_parent(platform, name):
    return bool(re.fullmatch({'cisco_xr': r'bundle-ether\d+', 'huawei_vrp': r'Eth-Trunk\d+',
                             'ubiquiti_edgeswitch': r'3/\d+'}.get(platform, r'port-channel\d+'), name, re.I))


def parse_aggregation(output, context, observed=(), *, collection_time='', complete=None):
    """Parse complete interface stanzas, never operational state or descriptions.

    Completeness requires the platform's final configuration terminator. Partial
    stanzas retain affirmative bindings but cannot prove any parent empty.
    Duplicate/contradictory bindings are reported and excluded rather than guessed.
    """
    platform = context.platform
    edge = platform == 'ubiquiti_edgeswitch'
    if complete is None:
        complete = bool(re.search(r'(?m)^\s*(?:return|end)\s*$', output))
        # FASTPATH exports can close the outer configure context with exit,
        # rather than using an IOS-style end marker. Require balanced contexts.
        if edge and not complete:
            depth, opened, closed = 0, False, False
            for line in output.splitlines():
                text = line.strip()
                if text == 'configure' and depth == 0 and not opened:
                    depth, opened = 1, True
                elif opened and (text.startswith('interface ') or text == 'vlan database'):
                    depth += 1
                elif opened and text == 'exit':
                    depth -= 1
                    closed = depth == 0
                elif closed and text and not text.startswith('!'):
                    closed = False
            complete = opened and closed and depth == 0
    complete = bool(complete and re.search(
        r'(?im)^\s*(?:interface\s+|hostname\s+|sysname\s+|version\s+|'
        r'vlan\s+|l2vpn(?:\s|$)|vsi\s+|bridge-domain\s+|Building configuration|Current configuration|!Current Configuration|!! IOS)', output))
    problems = []
    if not output.strip() or re.search(r'(?im)^\s*(?:%.*(?:Invalid|Error|Unknown)|Error:|Invalid command)', output):
        raise ValueError('aggregation configuration unavailable')
    stanzas = {}
    current, lines = None, []
    def finish():
        nonlocal current, lines, complete
        if current is not None:
            if current in stanzas:
                problems.append('duplicate interface stanza')
                complete = False
            stanzas.setdefault(current, []).extend(lines)
        current, lines = None, []
    output = re.sub(r"-----BEGIN [^-]*PRIVATE KEY-----.*?(?:-----END [^-]*PRIVATE KEY-----|\Z)", "[REDACTED PRIVATE KEY]", output, flags=re.S)
    for raw in output.splitlines():
        heading = re.fullmatch(r'\s*interface\s+(.+?)\s*', raw)
        if heading:
            finish()
            original = heading[1].split(' l2transport')[0]
            current = identity(platform, original)
            lines = [raw]
        elif current is not None:
            if (raw.strip() == 'exit' if edge else raw in {'!', '#', 'end', 'return'}):
                lines.append(raw)
                finish()
            elif raw and not raw[0].isspace() and not edge:
                finish()
            else:
                lines.append(raw)
    if current is not None:
        finish()
        complete = False
    parents = {identity(platform, n) for n in observed if is_parent(platform, identity(platform, n))}
    parents.update(n for n in stanzas if is_parent(platform, n))
    bindings = []
    pattern = {'cisco_xr': r'bundle id (\d+)(?:\s+.*)?', 'huawei_vrp': r'eth-trunk (\d+)',
               'ubiquiti_edgeswitch': r'addport 3/(\d+)'}.get(platform, r'channel-group (\d+)(?:\s+.*)?')
    for name, body in stanzas.items():
        if '.' in name or is_parent(platform, name):
            continue
        if not re.fullmatch(r'(?:gigabitethernet|tengige|fastethernet|ethernet|hundredgige|fortygige)\d[\d/]*|0/\d+', name, re.I):
            continue
        numbers = {m[1] for line in body[1:] if (m := re.fullmatch(pattern, line.strip(), re.I))}
        label = {'cisco_xr': 'bundle id', 'huawei_vrp': 'eth-trunk',
                 'ubiquiti_edgeswitch': 'addport'}.get(platform, 'channel-group')
        if any(re.match(re.escape(label) + r'(?:\s|$)', line.strip()) and not re.fullmatch(pattern, line.strip(), re.I) for line in body[1:]):
            complete = False
            problems.append('malformed member binding')
        if len(numbers) > 1:
            complete = False
            problems.append('contradictory member binding')
        elif numbers:
            parent = parent_name(platform, next(iter(numbers)))
            if parent not in parents:
                complete = False
                problems.append('unobserved aggregate parent')
            bindings.append((name, parent))
    subs = tuple(sorted((n, n.split('.')[0]) for n in stanzas if '.' in n and is_parent(platform, n.split('.')[0])))
    if not complete:
        problems.append('incomplete member configuration')
    evidence = tuple((n, '\n'.join(_safe_source(re.sub(r'(?i)((?:uisp|api)[-_ ]?key)(?:\s*[:=]\s*|\s+).*', r'\1 [REDACTED]', line), platform) for line in body)) for n, body in sorted(stanzas.items()))
    return AggregationSnapshot(context.device_id, platform, collection_time, bool(complete), tuple(sorted(parents)),
                               tuple(sorted(bindings)), subs, evidence, tuple(sorted(set(problems))), context.device_family,
                               "display current-configuration" if platform == "huawei_vrp" else "show running-config")
