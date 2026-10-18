"""Vendor MAC command lifecycle and strict, offline table parsers."""
from contextlib import contextmanager
import re

from orbitflow.capabilities.mac import MacEntry, MacSnapshot, normalize_mac


@contextmanager
def operational_cli(session, platform, *, cli=None, timeout=30):
    if platform.startswith('cisco_'):
        from orbitflow.vendors.cisco.ios import open_cisco_cli, CiscoIOSCLI
        from orbitflow.vendors.cisco.interfaces import CiscoXRCLI
        with open_cisco_cli(session, cli=cli, cli_type=CiscoXRCLI if platform == 'cisco_xr' else CiscoIOSCLI, timeout=timeout) as shell:
            yield shell
    else:
        from orbitflow.vendors.common import open_prompt_cli
        with open_prompt_cli(session, cli=cli, timeout=timeout,
                             prompt_pattern=r'^([^\r\n]*(?:<[^<>\r\n]+>|\[[^\[\]\r\n]+\]))[ \t]*$' if platform == 'huawei_vrp' else r'^([^\r\n]+[>#])[ \t]*$',
                             rejected=lambda text: bool(re.search(r'(?i)error|invalid|unknown command', text)),
                             platform_name=platform,
                             paging_command='screen-length 0 temporary' if platform == 'huawei_vrp' else 'terminal length 0') as shell:
            yield shell


def parse_table(output, platform):
    if re.search(r'(?i)(?:invalid input|unknown command|unrecognized command|incomplete command|--more--|error:|command not found)', output):
        raise ValueError('MAC command failed or incomplete')
    headers = {'cisco_ios': r'Vlan\s+Mac Address\s+Type\s+Ports|BD\s+mac addr\s+type\s+ports',
               'cisco_xe': r'Vlan\s+Mac Address\s+Type\s+Ports|BD\s+mac addr\s+type\s+ports',
               'cisco_xr': r'Mac Address\s+Type\s+Learned from/Filtered on',
               'huawei_vrp': r'MAC Address\s+VLAN/\s+PEVLAN\s+CEVLAN\s+Port\s+Type',
               'ubiquiti_edgeswitch': r'VLAN ID\s+MAC Address\s+Interface\s+IfIndex\s+Status'}
    if platform not in headers or not re.search(headers[platform], output, re.I):
        raise ValueError('Unrecognized MAC table')
    if platform == 'huawei_vrp' and not re.search(r'VSI/SI\s+MAC-Tunnel', output, re.I):
        raise ValueError('Truncated Huawei MAC header')
    entries, scoped, total, slot, xr_scope = [], [], None, '', ''
    started = False
    for raw in output.splitlines():
        line = raw.strip()
        if platform == 'cisco_xr' and re.match(r'(?i)Bridge[- ](?:domain|group):', line):
            xr_scope = line
            continue
        if re.search(headers[platform], line, re.I):
            started = True
            continue
        m = re.search(r'MAC address table of slot (\d+):', line, re.I)
        if m:
            slot = m[1]
            continue
        m = re.search(r'Total matching items on slot (\d+) displayed\s*=\s*(\d+)', line, re.I)
        if m:
            scoped.append(('slot ' + m[1], int(m[2])))
            continue
        m = re.search(r'Total Mac Addresses for this criterion:\s*(\d+)', line, re.I)
        if m:
            total = int(m[1])
            continue
        if not started or not line or set(line) <= set('-= '):
            continue
        if platform == 'cisco_xr':
            m = re.match(r'([\da-f.]+)\s+(\S+)\s+(.+?)\s+N/A\s+', line, re.I)
            if not m:
                if re.search(r'(?i)resync|resynchron|location|bridge-domain|^Mac ', line):
                    continue
                raise ValueError('Malformed XR MAC row')
            if len(line[m.end():].split()) < 2:
                raise ValueError('Truncated XR MAC row')
            mac, kind, attachment = m.groups()
            domain, index = '', ''
        elif platform == 'huawei_vrp':
            if line.startswith(('VSI/SI', 'MAC-Tunnel')):
                continue
            m = re.fullmatch(r'([\da-f-]+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)', line, re.I)
            if not m:
                raise ValueError('Malformed Huawei MAC row')
            mac, domain, pe, ce, attachment, kind, index = m.groups()
            # Preserve outer/inner and LSP evidence separately from domain identity.
            index = f'PEVLAN={pe};CEVLAN={ce};LSP={index}'
        else:
            m = re.fullmatch(r'(\S+)\s+([\da-f.:]+)\s+(\S+)\s+(\S+)(?:\s+(\S+))?', line, re.I)
            if not m:
                raise ValueError('Malformed MAC row')
            domain, mac, third, fourth, fifth = m.groups()
            if platform == 'ubiquiti_edgeswitch':
                attachment, index, kind = third, fourth, fifth or ''
                if not kind:
                    raise ValueError('Truncated EdgeSwitch MAC row')
            else:
                kind, attachment, index = third, fourth, ''
        normalized_kind = {'learned': 'dynamic', 'dynamic': 'dynamic', 'static': 'static',
                           'management': 'management', 'evpn': 'remote', 'routed': 'routed'}.get(kind.lower(), 'unknown')
        entries.append(MacEntry(normalize_mac(mac), domain, attachment, kind, normalized_kind,
                                ('slot ' + slot if slot else xr_scope), index))
    return MacSnapshot(tuple(entries), total if total is not None else len(entries), tuple(scoped))
