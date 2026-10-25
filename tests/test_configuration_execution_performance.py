"""Synthetic profile/benchmark. Run with pytest -s; never opens a network socket."""
from collections import Counter
from contextlib import nullcontext
import json
import socket
from statistics import median
from time import perf_counter
from types import SimpleNamespace

import pytest

from orbitflow.configuration import execution as ex
from orbitflow.transport import DeviceSession
from orbitflow.vendors.common import DeviceCLI
from orbitflow.configuration.execution_observation import observation_scope
from orbitflow.logging import module_logger, sanitize_text
from orbitflow.timing import profiling
from test_configuration_execution import context
from test_interface_capability import CASES


class SyntheticChannel:
    def __init__(self, edge=False):
        self.prompt = '(fixture) #' if edge else 'fixture#'
        self.edge = edge
        self.sent = []
        self.pending = b''
        self.config_override = None

    def sendall(self, data):
        command = data.decode().strip()
        self.sent.append(command)
        if not command:
            self.pending = self.prompt.encode()
            return
        if command == 'show running-config':
            output = ('configure\nhostname fixture\nvlan database\n vlan 445\n vlan name 445 "Customer"\nexit\ninterface 0/1\n description original\n vlan pvid 445\n vlan participation include 445\nexit\nexit\n'
                      if self.edge else 'hostname fixture\nvlan 445\n name Customer\n!\ninterface Gi1/0/1\n description original\n switchport mode access\n switchport access vlan 445\n!\nend\n')
            output = self.config_override or output
        elif command == 'show interfaces description':
            output = CASES['cisco_ios']['output'].replace('Gi0/0/0', 'Gi1/0/1').replace('Customer uplink west', 'original')
        elif command == 'show interfaces status all':
            output = CASES['ubiquiti_edgeswitch']['output']
        elif command.startswith('show vlan'):
            output = ('VLAN ID: 445\nVLAN Name: Customer\nVLAN Type: Static\nInterface Current Configured Tagging\n--------- ------- ---------- --------\n0/1 Include Include Untagged'
                      if self.edge else 'VLAN Name Status Ports\n---- -------------------------------- --------- -------------------------------\n445 Customer active Gi1/0/1')
        elif command in {'terminal length 0', 'terminal width 511'}:
            output = ''
        else:
            raise AssertionError('unexpected synthetic command')
        self.pending = (command + '\n' + output + '\n' + self.prompt).encode()

    def recv(self, _size):
        value, self.pending = self.pending, b''
        if not value:
            raise socket.timeout()
        return value

    def settimeout(self, timeout):
        assert timeout > 0

    def close(self):
        pass


def synthetic(family):
    channel = SyntheticChannel(family == 'EdgeSwitch')
    session = DeviceSession(SimpleNamespace(invoke_shell=lambda: channel), lambda: None)
    return session, channel


@pytest.mark.parametrize('family', ['C3750X', 'C3850X', 'EdgeSwitch'])
@pytest.mark.parametrize('optimized', [False, True])
@pytest.mark.parametrize('profiled', [False, True])
def test_observation_profile_benchmark(family, optimized, profiled, tmp_path):
    """Ten row-shaped full-read epochs; durations are host-only, without latency."""
    ctx = context(family)
    entry = dict(request=dict(inputs=dict(vlan_id=445)))
    durations = []
    session, channel = synthetic(family)
    with module_logger('configuration', 'execution', log_root=tmp_path) as (logger, _), \
            profiling(logger, sanitize_text, run_id='synthetic') if profiled else nullcontext():
        durations, counts = benchmark_epochs(session, channel, ctx, entry, optimized)
    assert counts['terminal length 0'] == (2 if optimized else 31)
    assert counts['show running-config'] == 10
    print(json.dumps(dict(family=family, optimized=optimized, profiled=profiled, epochs=10, commands=sum(counts.values()),
                         paging=counts['terminal length 0'], full_config=counts['show running-config'],
                         median_seconds=median(durations), p95_seconds=sorted(durations)[-1])))


def benchmark_epochs(session, channel, ctx, entry, optimized):
    durations = []
    with session, DeviceCLI(session) as cli:
        cli._reuse_session_setup = optimized
        with observation_scope(session, cli) if optimized else nullcontext():
            for _ in range(10):
                started = perf_counter()
                value = ex._observe(session, ctx, cli, [entry], 30)
                durations.append(perf_counter() - started)
                assert value['configuration_reliable']
                assert value['vlan_lookups']['445']['status'] == 'present'
    counts = Counter(channel.sent)
    return durations, counts

@pytest.mark.parametrize('family,function', [
    (family, function) for family in ('C3750X', 'C3850X', 'EdgeSwitch')
    for function in (('VLAN Database', 'VLAN Port', 'Interface Description') if family == 'EdgeSwitch'
                     else ('VLAN Database', 'Access Port', 'Trunk Port', 'Interface Description'))])
@pytest.mark.parametrize('staged', [False, True])
def test_template_stage_collection_schedule_benchmark(family, function, staged):
    """Real collector exchanges for ten independent rows; no writes or simulated RTT.

    Reproduce the pre-revision collector schedule versus the revised full-collection
    fallback stage schedule. Semantic execution is tested separately with real plans.
    """
    from orbitflow.configuration.v2.catalogue import CATALOGUE
    from orbitflow.capabilities.configuration import ConfigurationService
    from orbitflow.capabilities.vlans import VlanService
    from orbitflow.timing import command_category
    template = next(t for t in CATALOGUE if (t.family, t.function) == (family, function))
    ctx = context(family)
    from orbitflow.configuration.v2.planning import request
    entries = []
    for i in range(1, 11):
        inputs = dict(management_ip=ctx.management_ip)
        if function == 'VLAN Database':
            inputs.update(vlan_id=445, name='Customer')
        else:
            inputs['interface'] = f'0/{i}' if family == 'EdgeSwitch' else f'GigabitEthernet1/0/{i}'
            if function == 'Interface Description':
                inputs['description'] = 'new'
            elif function == 'Access Port':
                inputs['vlan_id'] = 445
            elif function == 'Trunk Port':
                inputs.update(action='Add', vlans=[445])
            else:
                inputs.update(action='Add/Change', tagged_vlans='445')
        entries.append(dict(request=request(template.id, inputs, row=i+2),
                       identity=dict(platform=ctx.platform), result=dict(dependencies=[])))
    # Database rows with independent IDs share a stage. The fixture returns a
    # constant lookup body; this benchmark measures exchanges, not verification.
    if function == 'VLAN Database':
        for i, entry in enumerate(entries, 445):
            entry['request']['inputs']['vlan_id'] = i
    assert len(list(ex._template_stages(entries))) == 1
    durations = []
    for _ in range(5):
        session, channel = synthetic(family)
        started = perf_counter()
        with session, DeviceCLI(session) as cli, observation_scope(session, cli):
            cli._reuse_session_setup = True
            ex._observe(session, ctx, cli, entries, 30)  # Mandatory initial baseline.
            ConfigurationService(timeout=30).collect(session, ctx, cli=cli)  # Protected backup read.
            for group in ([entries] if staged else [[entry] for entry in entries]):
                if not staged:
                    ex._observe(session, ctx, cli, group, 30)
                if function == 'VLAN Database':
                    for entry in group:
                        VlanService(timeout=30).lookup(session, ctx, entry['request']['inputs']['vlan_id'], cli=cli)
                else:
                    ex._observe(session, ctx, cli, group, 30)
            # Operational verification remains per target for port templates.
            # Counted separately by semantic executor tests; this synthetic channel
            # deliberately only implements observation/lookup commands.
        durations.append(perf_counter() - started)
    counts = Counter(channel.sent)
    expected = (2 if function == 'VLAN Database' else 3) if staged else (12 if function == 'VLAN Database' else 22)
    assert counts['show running-config'] == expected
    categories = Counter(command_category(command) for command in channel.sent if command)
    print(json.dumps(dict(benchmark='template_stage_collection_schedule', family=family, template=template.id,
        staged=staged, rows=10, samples=5, full_config=counts['show running-config'],
        targeted_interface_reads=categories['interface_read'], targeted_vlan_reads=categories['vlan_read'],
        median_seconds=median(durations), p95_seconds=sorted(durations)[-1])))
