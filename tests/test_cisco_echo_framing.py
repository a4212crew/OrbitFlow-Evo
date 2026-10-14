"""Shared-reader wire fixtures; no device access."""
import socket

import pytest

from orbitflow.vendors.common import DeviceCLI, InteractiveCLIError, InteractiveCLITimeout
from orbitflow.vendors.cisco.ios import open_cisco_cli
from orbitflow.vendors.cisco.vlans import CiscoVlanAdapter
from test_shared_cli import device_session
from test_capability_context import DEVICES


def wire_cli():
    session, client, channel = device_session(DEVICES[0])
    return session, channel


def inject(channel, command, chunks):
    original = channel.sendall
    def send(data):
        if data == (command + "\n").encode():
            channel.sent.append(command)
            channel.pending = list(chunks)
        else:
            original(data)
    channel.sendall = send


@pytest.mark.parametrize("sid,port", [(2324, "TenGigabitEthernet0/1"),
                                       (1234, "TenGigabitEthernet0/0/24")])
@pytest.mark.parametrize("style", ["full", "clipped", "wrapped", "clipped_wrapped"])
@pytest.mark.parametrize("split", [False, True])
def test_owner_absence_shared_reader(sid, port, style, split):
    session, channel = wire_cli()
    with session, DeviceCLI(session) as cli:
        # Exact owner ME prompt; ASR hostname is deliberately synthetic.
        cli.prompt = "T-COBUR-35PENT-RTR1#"
        channel.prompt = cli.prompt
        command = f"show ethernet service instance id {sid} interface {port} detail"
        echo = command if not style.startswith("clipped") else "$ " + command.split("service ")[1]
        if "wrapped" in style:
            echo = echo[:40] + "\r\n" + echo[40:]
        body = f"Service Instance ID {sid} on interface {port} does not exist"
        wire = f"{cli.prompt}{echo}\r\n{body}\r\n{cli.prompt}".encode()
        chunks = [wire[i:i+1] for i in range(len(wire))] if split else [wire]
        inject(channel, command, chunks)
        result = CiscoVlanAdapter(session, cli=cli).service_detail(port, sid)
        assert result["status"] == "absent"
        assert result["evidence"] and not result["facts"]
        assert not channel.pending


@pytest.mark.parametrize("echo", ["sw#$ detail", "other#$ instance id 2324 interface TenGigabitEthernet0/1 detail",
    "sw#$ instance id 1234 interface TenGigabitEthernet0/1 detail",
    "sw#$ instance id 2324 interface TenGigabitEthernet0/2 detail",
    "sw#show unrelated\r\nsw#$ instance id 2324 interface TenGigabitEthernet0/1 detail"])
@pytest.mark.parametrize("ending", [b"", socket.timeout()])
def test_mismatch_fails_closed(echo, ending):
    session, channel = wire_cli()
    command = "show ethernet service instance id 2324 interface TenGigabitEthernet0/1 detail"
    with session, DeviceCLI(session) as cli:
        with open_cisco_cli(session, cli=cli):
            inject(channel, command, [(echo + "\r\nstale\r\nsw#").encode(), ending])
            with pytest.raises(InteractiveCLIError):
                cli.run_command(command)
            sent = list(channel.sent)
            with pytest.raises(InteractiveCLIError, match="unsynchronized"):
                cli.run_command(command)
            assert channel.sent == sent


def test_large_wrapped_configuration_preserves_body_and_delayed_prompt():
    session, channel = wire_cli()
    command = "show running-config"
    body = "\n" + "  description " + "x" * 2000 + "  \n"
    body += "interface fixture\n" * 10000 + "banner motd ^\nsw#\n^\nend\n"
    with session, DeviceCLI(session) as cli:
        with open_cisco_cli(session, cli=cli):
            wire = ("sw#show running-\r\nconfig\r\n" + body.replace("\n", "\r\n") + "\r\n").encode()
            inject(channel, command, [wire[i:i+4093] for i in range(0, len(wire), 4093)]
                   + [b"sw", b"#", socket.timeout()])
            assert cli.read_configuration(command) == body


def test_timeout_reports_safe_echo_stage():
    session, channel = wire_cli()
    with session, DeviceCLI(session) as cli:
        inject(channel, "show version", [b"fixture-secret-output\r\nsw#", socket.timeout()])
        with pytest.raises(InteractiveCLITimeout, match="stage=echo") as error:
            cli.run_command("show version")
        assert "fixture-secret" not in str(error.value)


@pytest.mark.parametrize("device_index", [4, 5])
def test_clipped_echo_is_not_enabled_for_other_vendor_shells(device_index):
    session, _, channel = device_session(DEVICES[device_index])
    with session, DeviceCLI(session) as cli:
        command = "show version"
        inject(channel, command, [(cli.prompt + "$ version\r\nbody\r\n" + cli.prompt).encode(), socket.timeout()])
        with pytest.raises(InteractiveCLITimeout, match="stage=echo"):
            cli.run_command(command)


def test_standalone_cisco_adapter_uses_shared_framing():
    session, channel = wire_cli()
    command = "show ethernet service instance id 2324 interface TenGigabitEthernet0/1 detail"
    inject(channel, command, [b"sw#$ instance id 2324 interface TenGigabitEthernet0/1 detail\r\n"
                             b"Service Instance ID 2324 on interface TenGigabitEthernet0/1 does not exist\r\nsw#"])
    with session:
        assert CiscoVlanAdapter(session).service_detail("TenGigabitEthernet0/1", 2324)["status"] == "absent"
    assert channel.close_calls == 1


@pytest.mark.parametrize("sample_index", [0, 2])
def test_present_service_through_wrapped_shared_reader(sample_index):
    from test_cisco_evc_service_detail import SAMPLES, response
    sample = SAMPLES[sample_index]
    _, _, port, sid, *_ = sample
    command = f"show ethernet service instance id {sid} interface {port} detail"
    session, channel = wire_cli()
    with session, DeviceCLI(session) as cli:
        echo = command[:30] + "\r\n" + command[30:]
        inject(channel, command, [("sw#" + echo + "\r\n" + response(sample)
                                  + "\r\nsw#").encode()])
        assert CiscoVlanAdapter(session, cli=cli).service_detail(port, sid)["status"] == "present"
