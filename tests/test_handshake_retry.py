"""Exercise real Windows wrapping, shared authentication and retry ownership."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import paramiko
import pytest

from orbitflow.configuration_backup import failure_reason
from orbitflow.transport import connect_device, DeviceCredentials, TransportConfig
from orbitflow.transport import windows
from orbitflow.transport.exceptions import DeviceConnectionError, ConnectionRetryExhausted


def lost_session(client, underlying=None):
    transport = SimpleNamespace(active=False, initial_kex_done=False,
                                get_exception=lambda: underlying)
    client.get_transport.return_value = transport
    # Use the real Paramiko raising site; matching arbitrary SSH error text is
    # deliberately insufficient to authorize a connection retry.
    paramiko.Transport.get_remote_server_key(transport)


@pytest.mark.parametrize('recover', [True, False])
@pytest.mark.parametrize('underlying', [None, EOFError(), TimeoutError(), ConnectionResetError()])
def test_windows_handshake_retry_cleanup(monkeypatch, recover, underlying):
    clients = [MagicMock(), MagicMock()]
    processes = [MagicMock(), MagicMock()]
    sockets = [MagicMock(), MagicMock()]
    for process in processes:
        process.poll.return_value = None
    starts = []
    monkeypatch.setattr('orbitflow.transport.wait_for_connection_start', lambda: starts.append(1))
    monkeypatch.setattr(windows, '_free_local_port', lambda: 49152)
    popen = MagicMock(side_effect=processes)
    monkeypatch.setattr(windows.subprocess, 'Popen', popen)
    monkeypatch.setattr(windows, '_open_forwarded_socket', MagicMock(side_effect=sockets))
    created = []

    def client_factory():
        if created:
            clients[0].close.assert_called_once()
            sockets[0].close.assert_called_once()
            processes[0].terminate.assert_called_once()
            processes[0].wait.assert_called_once()
        client = clients[len(created)]
        created.append(client)
        return client

    monkeypatch.setattr(windows.paramiko, 'SSHClient', client_factory)
    clients[0].connect.side_effect = lambda *a, **k: lost_session(clients[0], underlying)
    if not recover:
        clients[1].connect.side_effect = lambda *a, **k: lost_session(clients[1], underlying)
    config = TransportConfig('proxy', 'cluster', 'bastion', 'user', tsh_path='tsh')
    credentials = DeviceCredentials('user', password='synthetic-login', secret='synthetic-enable')
    if recover:
        with connect_device('192.0.2.1', credentials, config, system='windows'):
            pass
    else:
        with pytest.raises(ConnectionRetryExhausted) as caught:
            connect_device('192.0.2.1', credentials, config, system='windows')
        assert failure_reason('connect', caught.value) == 'Transient connection failure after two attempts.'
        assert 'synthetic' not in str(caught.value)
    assert len(created) == len(starts) == 2
    for index in range(2):
        clients[index].close.assert_called_once()
        sockets[index].close.assert_called_once()
        processes[index].terminate.assert_called_once()
        assert clients[index].connect.call_args.kwargs['sock'] is sockets[index]
        assert clients[index].connect.call_args.args == ('192.0.2.1',)
        command = popen.call_args_list[index].args[0]
        assert command == ['tsh', 'ssh', '--cluster', 'cluster', '--proxy', 'proxy',
                           '-N', '-L', '127.0.0.1:49152:192.0.2.1:22', 'user@bastion']


@pytest.mark.parametrize('error', [
    paramiko.BadAuthenticationType('synthetic', ['publickey']),
    paramiko.AuthenticationException('synthetic'),
    paramiko.BadHostKeyException('device', MagicMock(), MagicMock()),
    paramiko.SSHException("Server 'device' not found in known_hosts"),
    paramiko.SSHException('No existing session'),
    paramiko.SSHException('unclassified protocol failure'),
])
@pytest.mark.parametrize('during_key_retrieval', [False, True])
def test_windows_nonretryable_ssh_failures(monkeypatch, error, during_key_retrieval):
    client, process, sock = MagicMock(), MagicMock(), MagicMock()
    process.poll.return_value = None
    monkeypatch.setattr('orbitflow.transport.wait_for_connection_start', lambda: None)
    monkeypatch.setattr(windows, '_free_local_port', lambda: 49152)
    popen = MagicMock(return_value=process)
    monkeypatch.setattr(windows.subprocess, 'Popen', popen)
    monkeypatch.setattr(windows, '_open_forwarded_socket', lambda *a: sock)
    monkeypatch.setattr(windows.paramiko, 'SSHClient', lambda: client)
    if during_key_retrieval:
        client.connect.side_effect = lambda *a, **k: lost_session(client, error)
    else:
        client.connect.side_effect = error
    with pytest.raises(DeviceConnectionError):
        connect_device('192.0.2.1', DeviceCredentials('user'),
                       TransportConfig('proxy', 'cluster', 'bastion', 'user', tsh_path='tsh'),
                       system='windows')
    popen.assert_called_once()
    client.connect.assert_called_once()
    client.close.assert_called_once()
    sock.close.assert_called_once()
    process.terminate.assert_called_once()
