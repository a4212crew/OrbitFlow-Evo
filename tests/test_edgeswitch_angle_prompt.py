"""Synthetic complete login banners; no hardware or secret-bearing output."""
import pytest

from orbitflow.capabilities import InterfaceService, VlanService
from orbitflow.capabilities.configuration import ConfigurationService
from orbitflow.compliance import evaluate_vlan_compliance
from orbitflow.inventory import DeviceInventoryResolver, JsonInventoryStore
from orbitflow.vendors.common import DeviceCLI, InteractiveCLITimeout
from orbitflow.vendors.privilege import EnableAuthenticationFailed, MissingEnableSecret
from orbitflow.vendors.prompts import is_structural_prompt
from orbitflow.vendors.ubiquiti.prompts import extract_edgeswitch_hostname
from test_capability_context import DEVICES
from test_device_access import enable_session, SECRET
from test_prompt_banners import banner_chunks
from test_vlan_compliance import POLICY


EDGE = next(d for d in DEVICES if d[1] == 'ubiquiti_edgeswitch')
BANNER = (b'\r\nUbiquiti Networks, Inc.\r\nEdgeSwitch 24\r\n'
          b'****************************************\r\n'
          b'* Authorized access only *\r\n'
          b'****************************************\r\n')
CONFIG = ('vlan database\n vlan 445,545,2449\nexit\n'
          'interface 0/1\n description "Synthetic uplink"\n'
          ' vlan participation include 445,545,2449\n'
          ' vlan tagging 445,545,2449\nexit\n')


def login(channel, layout):
    original = channel.sendall

    def send(data):
        original(data)
        if data == b'\n':
            payload = BANNER + channel.prompt.encode()
            channel.pending = ([payload] if layout == 'combined' else
                               [bytes([byte]) for byte in payload])
    channel.sendall = send


@pytest.mark.parametrize('layout', ['combined', 'bytes'])
@pytest.mark.parametrize('user_exec', [False, True])
@pytest.mark.parametrize('wrapped', [False, True])
def test_banner_identity_enable_observations_compliance_and_backup(tmp_path, layout, user_exec, wrapped):
    session, client, channel = enable_session(EDGE)
    host = '<LAB-ES24>' if wrapped else 'LAB-ES24'
    channel.prompt = f'({host}) ' + ('>' if user_exec else '#')
    channel.outputs['show running-config'] = CONFIG
    login(channel, layout)
    store = tmp_path / 'inventory.json'
    with session, DeviceCLI(session) as cli:
        assert cli.prompt == f'({host}) #'
        assert extract_edgeswitch_hostname(cli.prompt) == 'LAB-ES24'
        context = DeviceInventoryResolver(JsonInventoryStore(store)).resolve(
            session, management_ip='192.0.2.1', cli=cli)
        assert (context.hostname, context.platform, context.device_family) == (
            'LAB-ES24', 'ubiquiti_edgeswitch', 'EdgeSwitch')
        records = InterfaceService().collect(session, context, cli=cli)
        assert records and all(r.device_name == 'LAB-ES24' for r in records)
        vlans = VlanService().collect(session, context, cli=cli)
        assert vlans.device_name == 'LAB-ES24'
        findings = evaluate_vlan_compliance(context, records, vlans, POLICY)
        assert any(f['observed'].get('config_interface_name') == '0/1' for f in findings)
        assert ConfigurationService().collect(session, context, cli=cli) == CONFIG
        assert cli.run_command('show version') == EDGE[0]
        assert not channel.pending
        assert channel.sent.count('enable') == int(user_exec)
        assert channel.sent.count(SECRET) == int(user_exec)
        assert channel.sent.count('') == 1
    assert 'LAB-ES24' in store.read_text()
    assert SECRET not in store.read_text()
    assert client.opens == client.closes == channel.close_calls == 1
    assert session.secret is None


@pytest.mark.parametrize('layout', ['combined', 'bytes'])
@pytest.mark.parametrize('failure', ['denied', 'repeat', 'timeout', 'closed', 'identity', 'missing'])
def test_angle_user_exec_enable_fails_closed(layout, failure):
    session, client, channel = enable_session(
        EDGE, response=failure, secret=None if failure == 'missing' else SECRET)
    channel.prompt = '(<LAB-ES24>) >'
    if failure == 'identity':
        session, client, channel = enable_session(EDGE, enabled_prompt='(<OTHER>) #')
        channel.prompt = '(<LAB-ES24>) >'
    login(channel, layout)
    error = MissingEnableSecret if failure == 'missing' else EnableAuthenticationFailed
    with pytest.raises(error) as caught, session:
        DeviceCLI(session)
    assert SECRET not in str(caught.value)
    assert 'terminal length 0' not in channel.sent
    assert 'show version' not in channel.sent
    assert client.closes == channel.close_calls == 1
    assert session.secret is None


@pytest.mark.parametrize('prompt', [
    '(<LAB-ES24>) >', '(<LAB-ES24>) #',
    '(<LAB-ES24> (annotation (nested) # > text)) #',
])
def test_angle_prompt_structure(prompt):
    assert is_structural_prompt(prompt)
    assert extract_edgeswitch_hostname(prompt) == 'LAB-ES24'


@pytest.mark.parametrize('prompt', [
    '(<--->) #', '(<<LAB-ES24>>) #', '(<LAB-ES24) #',
    '(LAB-ES24>) #', '(<LAB-ES24> welcome) #', 'Welcome (<LAB-ES24>) #',
])
def test_decorative_and_malformed_banner_fails_initial_probe(prompt):
    session, client, channel = enable_session(EDGE)
    original = channel.sendall

    def send(data):
        original(data)
        if data == b'\n':
            channel.pending = banner_chunks(prompt, 'combined') + [TimeoutError()]
    channel.sendall = send
    assert not is_structural_prompt(prompt)
    with pytest.raises(InteractiveCLITimeout), session:
        DeviceCLI(session)
    assert channel.sent == ['']
    assert client.closes == channel.close_calls == 1
