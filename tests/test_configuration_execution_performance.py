"""Synthetic profile/benchmark. Run with pytest -s; never opens a network socket."""
from collections import Counter
from contextlib import nullcontext
import json
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
            output = ('hostname fixture\nvlan database\n vlan 445\n vlan name 445 "Customer"\nexit\ninterface 0/1\n description original\n vlan pvid 445\n vlan participation include 445\nexit\n'
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
        assert value
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
