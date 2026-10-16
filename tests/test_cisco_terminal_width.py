"""Synthetic wrapping proves the failure mechanism, not the original device bytes."""
import socket
from types import SimpleNamespace

import pytest

from orbitflow.capabilities import VlanService
from orbitflow.vendors.common import DeviceCLI, InteractiveCLIError
from orbitflow.vendors.cisco.ios import CiscoIOSCLI, CiscoIOSCLIError, open_cisco_cli
from orbitflow.vendors.cisco.interfaces import CiscoXRCLI
from test_shared_cli import Channel, OneShellClient
from orbitflow.transport import DeviceSession


class WidthChannel(Channel):
    def __init__(self, prompt='router#', setup=''):
        super().__init__(prompt, {'': '', 'terminal length 0': '',
                                 'terminal width 511': setup, 'show clock': '12:00'})
        self.wide = False
        self.wrap = False

    def recv(self, size):
        if not self.pending:
            raise socket.timeout()
        return super().recv(size)

    def sendall(self, data):
        command = data.decode().strip()
        if command.startswith('show ethernet'):
            port = command.split(' interface ')[1].split()[0]
            self.outputs[command] = (f'Service Instance ID: 545\nAssociated Interface: {port}\n'
                                     'Encapsulation: dot1q 545\nState: Up\n'
                                     'Microblock type: Bridge-domain\nBridge-domain: 545')
        super().sendall(data)
        if command == 'terminal width 511' and self.outputs[command] == '':
            self.wide = True
        if command.startswith('show ethernet') and (not self.wide or self.wrap):
            # A synthetic CRLF inside the echo prevents an exact line match.
            self.pending[1] = f'\r\n{command[:60]}\r\n{command[60:]}\r\n'.encode()
            self.pending.append(socket.timeout())


def session_for(channel):
    client = OneShellClient(channel)
    return DeviceSession(client, client.close)


@pytest.mark.parametrize('platform,prompt', [
    pytest.param('cisco_ios', 'router#', id='ME3600X'),
    pytest.param('cisco_ios', 'router#', id='C3750X'),
    pytest.param('cisco_xe', 'router#', id='C3850'),
    pytest.param('cisco_xe', 'router#', id='ASR920'),
    pytest.param('cisco_xr', 'RP/0/RP0/CPU0:router#', id='NCS540'),
])
@pytest.mark.parametrize('borrowed', [False, True])
def test_setup_short_commands_and_reconfiguration(platform, prompt, borrowed):
    channel = WidthChannel(prompt)
    session = session_for(channel)
    if borrowed:
        with DeviceCLI(session) as cli:
            for _ in range(2):
                with open_cisco_cli(session, cli=cli) as shell:
                    assert shell.run_command('show clock') == '12:00'
            assert channel.sent.count('terminal width 511') == 1
            assert not channel.close_calls
    else:
        factory = CiscoXRCLI if platform == 'cisco_xr' else CiscoIOSCLI
        shell = factory(session)
        assert shell.run_command('show clock') == '12:00'
        shell.close()
    assert channel.close_calls == 1


@pytest.mark.parametrize('family,port', [('ME3600X', 'GigabitEthernet0/24'),
                                       ('ASR920', 'TenGigabitEthernet0/0/24')])
@pytest.mark.parametrize('borrowed', [False, True])
def test_full_interface_detail_through_public_service(family, port, borrowed):
    channel = WidthChannel()
    session = session_for(channel)
    cli = DeviceCLI(session) if borrowed else None
    try:
        for _ in range(2 if borrowed else 1):
            detail = VlanService().service_detail(session, SimpleNamespace(device_family=family),
                                                 port, 545, cli=cli)
            assert (detail['status'], detail['operational_status']) == ('present', 'up')
        assert channel.sent.count('terminal width 511') == 1
    finally:
        if cli:
            cli.close()
    assert channel.close_calls == 1


@pytest.mark.parametrize('prompt', ['router#', 'RP/0/RP0/CPU0:router#'])
@pytest.mark.parametrize('setup', ['% Invalid input', '% Authorization failed',
                                   '% Ambiguous command', '% Command authorization failed',
                                   'Fri Oct 16 12:00:00.000 UTC\n% Invalid input', socket.timeout()])
@pytest.mark.parametrize('borrowed', [False, True])
def test_width_failure_blocks_commands_and_cleanup(setup, borrowed, prompt):
    channel = WidthChannel(prompt, setup=setup)
    session = session_for(channel)
    if borrowed:
        with DeviceCLI(session) as cli:
            with pytest.raises((InteractiveCLIError, TimeoutError), match="terminal width 511"):
                with open_cisco_cli(session, cli=cli):
                    pytest.fail('failed setup must not yield')
            sent = list(channel.sent)
            with pytest.raises(InteractiveCLIError, match='unsynchronized'):
                cli.run_command('show clock')
            assert channel.sent == sent
    else:
        with pytest.raises((CiscoIOSCLIError, TimeoutError), match="terminal width 511"):
            CiscoIOSCLI(session)
    assert 'show clock' not in channel.sent
    assert channel.close_calls == 1


@pytest.mark.parametrize('borrowed', [False, True])
def test_wrapped_echo_is_never_accepted_or_reused(borrowed):
    channel = WidthChannel()
    session = session_for(channel)
    shell = DeviceCLI(session) if borrowed else CiscoIOSCLI(session)
    channel.wrap = True
    command = 'show ethernet service instance id 545 interface GigabitEthernet0/24 detail'
    try:
        with pytest.raises(TimeoutError):
            shell.run_command(command)
        sent = list(channel.sent)
        with pytest.raises((InteractiveCLIError, CiscoIOSCLIError), match='unsynchronized'):
            shell.run_command('show clock')
        assert channel.sent == sent
    finally:
        shell.close()


def test_configuration_capture_uses_vendor_width_policy_and_cache():
    from orbitflow.capabilities.configuration import ConfigurationService
    channel = WidthChannel('RP/0/RP0/CPU0:router#')
    channel.outputs['show running-config'] = 'interface GigabitEthernet0/0/0/1\n!'
    session = session_for(channel)
    with DeviceCLI(session) as cli:
        service = ConfigurationService()
        context = SimpleNamespace(platform='cisco_xr')
        assert service.collect(session, context, cli=cli).startswith('interface ')
        assert service.collect(session, context, cli=cli).startswith('interface ')
        assert channel.sent.count('terminal width 511') == 1


def test_configuration_width_rejection_after_xr_timestamp():
    from orbitflow.capabilities.configuration import ConfigurationService
    channel = WidthChannel('RP/0/RP0/CPU0:router#',
                           'Fri Oct 16 12:00:00.000 UTC\n% Invalid input')
    session = session_for(channel)
    with DeviceCLI(session) as cli:
        with pytest.raises(InteractiveCLIError, match='terminal width 511'):
            ConfigurationService().collect(session, SimpleNamespace(platform='cisco_xr'), cli=cli)
        assert 'show running-config' not in channel.sent
