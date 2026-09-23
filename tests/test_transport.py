from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

import paramiko
import pytest

from orbitflow.transport import (
    DeviceConnectionError,
    DeviceCredentials,
    TransportConfig,
    TransportConfigurationError,
    TunnelError,
    UnsupportedPlatformError,
    connect_device,
)
from orbitflow.transport.linux import connect_linux
from orbitflow.transport.windows import _open_forwarded_socket, connect_windows


@pytest.fixture
def credentials():
    return DeviceCredentials(username="device-user", password="not-a-real-password")


@pytest.fixture
def config():
    return TransportConfig(
        proxy="teleport.example.test:443",
        cluster="example-cluster",
        bastion_host="example-bastion",
        bastion_user="teleport-user",
        teleport_key_path=Path("/profile/key"),
        teleport_cert_path=Path("/profile/key-cert.pub"),
        tsh_path="/usr/bin/tsh",
    )


def test_connect_device_dispatches_without_exposing_os_details(credentials, config):
    expected = MagicMock()
    with patch(
        "orbitflow.transport.windows.connect_windows", return_value=expected
    ) as connect:
        result = connect_device("192.0.2.10", credentials, config, system="Windows")
    assert result is expected
    connect.assert_called_once_with("192.0.2.10", credentials, config)


def test_connect_device_rejects_unsupported_os(credentials, config):
    with pytest.raises(UnsupportedPlatformError):
        connect_device("192.0.2.10", credentials, config, system="Darwin")


def test_host_key_verification_defaults_are_permissive(config):
    assert config.verify_bastion_host_key is False
    assert config.verify_device_host_key is False


@patch("orbitflow.transport.windows.time.sleep")
@patch("orbitflow.transport.windows.socket.create_connection")
def test_windows_forwarded_socket_retries_startup_failures(create_connection, sleep):
    forwarded_socket = MagicMock()
    create_connection.side_effect = [
        ConnectionRefusedError(),
        OSError("forward is starting"),
        forwarded_socket,
    ]
    process = MagicMock()
    process.poll.return_value = None

    result = _open_forwarded_socket(process, 49152, 15.0)

    assert result is forwarded_socket
    assert create_connection.call_count == 3
    assert sleep.call_count == 2
    forwarded_socket.recv.assert_not_called()
    forwarded_socket.close.assert_not_called()


@patch("orbitflow.transport.windows.time.sleep")
@patch(
    "orbitflow.transport.windows.time.monotonic",
    side_effect=[10.0, 10.0, 10.0, 10.3, 10.3],
)
@patch(
    "orbitflow.transport.windows.socket.create_connection",
    side_effect=ConnectionRefusedError(),
)
def test_windows_forwarded_socket_retries_are_bounded_by_connect_timeout(
    create_connection, monotonic, sleep
):
    process = MagicMock()
    process.poll.return_value = None

    with pytest.raises(TunnelError, match="timed out"):
        _open_forwarded_socket(process, 49152, 0.2)

    assert create_connection.call_args.args == (("127.0.0.1", 49152),)
    assert create_connection.call_args.kwargs["timeout"] == pytest.approx(0.2)
    sleep.assert_not_called()
    assert monotonic.call_count == 5


@patch("orbitflow.transport.windows.socket.create_connection")
def test_windows_tsh_exit_closes_socket_and_fails_cleanly(create_connection):
    forwarded_socket = create_connection.return_value
    process = MagicMock()
    process.poll.side_effect = [None, 1]

    with pytest.raises(TunnelError, match="exited before becoming ready"):
        _open_forwarded_socket(process, 49152, 15.0)

    create_connection.assert_called_once()
    forwarded_socket.close.assert_called_once_with()
    forwarded_socket.recv.assert_not_called()


@patch("orbitflow.transport.windows._open_forwarded_socket")
@patch("orbitflow.transport.windows._free_local_port", return_value=49152)
@patch("orbitflow.transport.windows.subprocess.Popen")
@patch("orbitflow.transport.windows.paramiko.SSHClient")
def test_windows_uses_tsh_forward_and_cleans_up(
    ssh_client,
    popen,
    _free_port,
    open_forwarded_socket,
    credentials,
    config,
):
    process = popen.return_value
    process.poll.return_value = None
    client = ssh_client.return_value
    forwarded_socket = open_forwarded_socket.return_value

    session = connect_windows("192.0.2.10", credentials, config)

    command = popen.call_args.args[0]
    assert command[:5] == [
        "/usr/bin/tsh",
        "ssh",
        "--cluster",
        "example-cluster",
        "--proxy",
    ]
    assert "127.0.0.1:49152:192.0.2.10:22" in command
    open_forwarded_socket.assert_called_once_with(process, 49152, 15.0)
    client.connect.assert_called_once_with(
        "192.0.2.10",
        port=22,
        username="device-user",
        password="not-a-real-password",
        pkey=None,
        sock=forwarded_socket,
        timeout=15.0,
    )
    client.load_system_host_keys.assert_not_called()
    assert isinstance(
        client.set_missing_host_key_policy.call_args.args[0], paramiko.AutoAddPolicy
    )

    session.close()
    session.close()
    client.close.assert_called_once_with()
    forwarded_socket.close.assert_called_once_with()
    process.terminate.assert_called_once_with()


@patch("orbitflow.transport.linux.paramiko.ProxyCommand")
@patch("orbitflow.transport.linux.paramiko.PKey.from_path")
@patch("orbitflow.transport.linux.paramiko.SSHClient")
def test_linux_uses_certificate_and_direct_tcpip(
    ssh_client, from_path, proxy_command, credentials, config
):
    bastion, target = MagicMock(), MagicMock()
    ssh_client.side_effect = [bastion, target]
    transport = bastion.get_transport.return_value
    transport.is_active.return_value = True
    channel = transport.open_channel.return_value
    key = from_path.return_value
    proxy = proxy_command.return_value

    session = connect_linux("192.0.2.10", credentials, config)

    from_path.assert_called_once_with(str(config.teleport_key_path))
    key.load_certificate.assert_called_once_with(str(config.teleport_cert_path))
    assert "tsh proxy ssh" in proxy_command.call_args.args[0]
    transport.open_channel.assert_called_once_with(
        "direct-tcpip", ("192.0.2.10", 22), ("127.0.0.1", 0)
    )
    assert target.connect.call_args.kwargs["sock"] is channel
    bastion.load_system_host_keys.assert_not_called()
    assert isinstance(
        bastion.set_missing_host_key_policy.call_args.args[0], paramiko.AutoAddPolicy
    )
    target.load_system_host_keys.assert_not_called()
    assert isinstance(
        target.set_missing_host_key_policy.call_args.args[0], paramiko.AutoAddPolicy
    )

    session.close()
    assert target.close.call_count == 1
    assert channel.close.call_count == 1
    assert bastion.close.call_count == 1
    assert proxy.close.call_count == 1


@patch("orbitflow.transport.linux.paramiko.ProxyCommand")
@patch("orbitflow.transport.linux.paramiko.PKey.from_path")
@patch("orbitflow.transport.linux.paramiko.SSHClient")
def test_linux_can_require_bastion_host_key_verification(
    ssh_client,
    _from_path,
    _proxy_command,
    credentials,
    config,
):
    bastion, target = MagicMock(), MagicMock()
    ssh_client.side_effect = [bastion, target]
    bastion.get_transport.return_value.is_active.return_value = True

    session = connect_linux(
        "192.0.2.10",
        credentials,
        replace(config, verify_bastion_host_key=True),
    )

    bastion.load_system_host_keys.assert_called_once_with()
    assert isinstance(
        bastion.set_missing_host_key_policy.call_args.args[0], paramiko.RejectPolicy
    )
    session.close()


@patch("orbitflow.transport.windows._open_forwarded_socket")
@patch("orbitflow.transport.windows._free_local_port", return_value=49152)
@patch("orbitflow.transport.windows.subprocess.Popen")
@patch("orbitflow.transport.windows.paramiko.SSHClient")
def test_windows_can_require_device_host_key_verification(
    ssh_client,
    popen,
    _free_port,
    _open_forwarded_socket,
    credentials,
    config,
):
    popen.return_value.poll.return_value = None
    client = ssh_client.return_value

    session = connect_windows(
        "192.0.2.10",
        credentials,
        replace(config, verify_device_host_key=True),
    )

    client.load_system_host_keys.assert_called_once_with()
    assert isinstance(
        client.set_missing_host_key_policy.call_args.args[0], paramiko.RejectPolicy
    )
    session.close()


@patch("orbitflow.transport.linux.paramiko.ProxyCommand")
@patch("orbitflow.transport.linux.paramiko.PKey.from_path")
@patch("orbitflow.transport.linux.paramiko.SSHClient")
def test_linux_can_skip_bastion_and_require_device_host_key_verification(
    ssh_client, _from_path, _proxy_command, credentials, config
):
    bastion, target = MagicMock(), MagicMock()
    ssh_client.side_effect = [bastion, target]
    bastion.get_transport.return_value.is_active.return_value = True

    session = connect_linux(
        "192.0.2.10",
        credentials,
        replace(
            config,
            verify_bastion_host_key=False,
            verify_device_host_key=True,
        ),
    )

    bastion.load_system_host_keys.assert_not_called()
    assert isinstance(
        bastion.set_missing_host_key_policy.call_args.args[0], paramiko.AutoAddPolicy
    )
    target.load_system_host_keys.assert_called_once_with()
    assert isinstance(
        target.set_missing_host_key_policy.call_args.args[0], paramiko.RejectPolicy
    )
    session.close()


def test_linux_requires_explicit_active_profile_paths(credentials, config):
    incomplete = TransportConfig(
        proxy=config.proxy,
        cluster=config.cluster,
        bastion_host=config.bastion_host,
        bastion_user=config.bastion_user,
        tsh_path=config.tsh_path,
    )
    with pytest.raises(TransportConfigurationError):
        connect_linux("192.0.2.10", credentials, incomplete)


@patch("orbitflow.transport.linux.paramiko.ProxyCommand")
@patch("orbitflow.transport.linux.paramiko.PKey.from_path")
@patch("orbitflow.transport.linux.paramiko.SSHClient")
def test_linux_reports_bastion_failure_as_teleport_error(
    ssh_client, _from_path, proxy_command, credentials, config
):
    from orbitflow.transport import TeleportError

    bastion = ssh_client.return_value
    bastion.connect.side_effect = OSError("authentication failed")

    with pytest.raises(TeleportError) as error:
        connect_linux("192.0.2.10", credentials, config)

    assert "authentication failed" not in str(error.value)
    bastion.close.assert_called_once_with()
    proxy_command.return_value.close.assert_called_once_with()


@patch("orbitflow.transport.windows._open_forwarded_socket")
@patch("orbitflow.transport.windows._free_local_port", return_value=49152)
@patch("orbitflow.transport.windows.subprocess.Popen")
@patch("orbitflow.transport.windows.paramiko.SSHClient")
def test_windows_cleans_up_after_target_authentication_failure(
    ssh_client,
    popen,
    _free_port,
    open_forwarded_socket,
    credentials,
    config,
):
    process = popen.return_value
    process.poll.return_value = None
    client = ssh_client.return_value
    client.connect.side_effect = paramiko.AuthenticationException("rejected")
    client.get_transport.return_value.is_active.return_value = True
    client.get_transport.return_value.auth_interactive.side_effect = (
        paramiko.AuthenticationException("interactive rejected")
    )

    with pytest.raises(
        DeviceConnectionError, match="failed to connect to target device"
    ):
        connect_windows("192.0.2.10", credentials, config)

    client.close.assert_called_once_with()
    open_forwarded_socket.return_value.close.assert_called_once_with()
    process.terminate.assert_called_once_with()


@patch("orbitflow.transport.linux.paramiko.ProxyCommand")
@patch("orbitflow.transport.linux.paramiko.PKey.from_path")
@patch("orbitflow.transport.linux.paramiko.SSHClient")
def test_linux_cleans_up_after_target_authentication_failure(
    ssh_client, _from_path, proxy_command, credentials, config
):
    bastion, target = MagicMock(), MagicMock()
    ssh_client.side_effect = [bastion, target]
    transport = bastion.get_transport.return_value
    transport.is_active.return_value = True
    channel = transport.open_channel.return_value
    target.connect.side_effect = paramiko.AuthenticationException("rejected")
    target.get_transport.return_value.is_active.return_value = True
    target.get_transport.return_value.auth_interactive.side_effect = (
        paramiko.AuthenticationException("interactive rejected")
    )

    with pytest.raises(
        DeviceConnectionError, match="failed to connect to target device"
    ):
        connect_linux("192.0.2.10", credentials, config)

    target.close.assert_called_once_with()
    channel.close.assert_called_once_with()
    bastion.close.assert_called_once_with()
    proxy_command.return_value.close.assert_called_once_with()
