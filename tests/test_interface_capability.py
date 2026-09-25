from datetime import datetime, timezone

import pytest

from orbitflow.capabilities import InterfaceCapabilityError, InterfaceService
from orbitflow.transport import DeviceSession
from orbitflow.vendors.cisco.interfaces import (
    extract_ios_xr_hostname,
    parse_ios_xr_interfaces_description,
    parse_interfaces_description,
)
from orbitflow.vendors.cisco.ios import extract_ios_hostname
from orbitflow.vendors.huawei.interfaces import (
    extract_huawei_hostname,
    parse_interface_brief,
    parse_interface_description,
)
from orbitflow.vendors.ubiquiti.interfaces import (
    extract_edgeswitch_hostname,
    parse_interfaces_status,
)


class FakeChannel:
    def close(self):
        self.closed = True

    def __init__(self, responses):
        self.responses = iter(responses)
        self.sent = []

    def sendall(self, data):
        self.sent.append(data)

    def settimeout(self, _timeout):
        pass

    def recv(self, _size):
        return next(self.responses)


def make_session(responses):
    channel = FakeChannel(responses)

    class Client:
        def invoke_shell(self, **_kwargs):
            return channel

    return DeviceSession(Client(), lambda: None), channel


CASES = {
    "cisco_ios": {
        "prompt": "ios#",
        "paging": "terminal length 0",
        "command": "show interfaces description",
        "output": (
            "Interface                      Status         Protocol Description\r\n"
            "Gi0/0/0                       up             up       Customer uplink west\r\n"
            "Gi0/0/1                       admin down     down     Spare port"
        ),
        "rejection": "% Invalid input detected at '^' marker.",
    },
    "cisco_xe": {
        "prompt": "xe#",
        "paging": "terminal length 0",
        "command": "show interfaces description",
        "output": (
            "Interface                      Status         Protocol Description\r\n"
            "Te0/0/0                       up             down     Metro handoff east"
        ),
        "rejection": "% Invalid input detected at '^' marker.",
    },
    "cisco_xr": {
        "prompt": "RP/0/RSP0/CPU0:xr#",
        "paging": "terminal length 0",
        "command": "show interfaces description",
        "output": (
            "Interface          Status      Protocol    Description\r\n"
            "Gi0/0/0/0          up          up          Core link north"
        ),
        "rejection": "% Invalid input detected at '^' marker.",
    },
    "huawei_vrp": {
        "prompt": "<NE05E>",
        "paging": "screen-length 0 temporary",
        "command": "display interface description",
        "output": (
            "Interface                         PHY   Protocol Description\r\n"
            "GE0/0/0                           up    up       Customer access one\r\n"
            "GE0/0/1                           *down down     Disabled spare port"
        ),
        "rejection": "Error: Unrecognized command found at '^' position.",
    },
    "ubiquiti_edgeswitch": {
        "prompt": "(C-HAWTH-382GLEN-BAS1) #",
        "paging": "terminal length 0",
        "command": "show interfaces status all",
        "output": (
            "                                         Link    Physical    Physical    Flow Control\r\n"
            "Port       Name                          State   Mode        Status      Status\r\n"
            "---------  ----------------------------  ------  ----------  ----------  ------------\r\n"
            "0/1        Unit 1                        Up      Auto        1000 Full   Inactive\r\n"
            "0/2        Unit 2                        Up      Auto        1000 Full   Inactive\r\n"
            "0/3        Unit 6                        Down    Auto                    Inactive\r\n"
            "0/7        Access_port                   Down    Auto                    Inactive\r\n"
            "0/13       Access_port                   Up      Auto        1000 Full   Inactive\r\n"
            "0/17                                     Down    Auto D                  Inactive\r\n"
            "3/1                                      Down\r\n"
            "3/2                                      Down\r\n"
            "\r\n"
            "Flow Control:Disabled"
        ),
        "rejection": "% Invalid input detected at '^' marker.",
    },
}


def run_collection(platform, output=None, setup_output="", device_name="edge-01"):
    case = CASES[platform]
    prompt = case["prompt"]
    paging = case["paging"]
    command = case["command"]
    session, channel = make_session(
        [
            prompt.encode(),
            f"{paging}\r\n{setup_output}\r\n{prompt}".encode(),
            f"{command}\r\n{case['output'] if output is None else output}\r\n{prompt}".encode(),
        ]
    )
    now = datetime(2026, 9, 20, 12, tzinfo=timezone.utc)
    records = InterfaceService(lambda: now).collect(
        session,
        device_ip="192.0.2.10",
        platform=platform,
        device_name=device_name,
    )
    return records, channel, now


@pytest.mark.parametrize("platform", CASES)
def test_every_platform_disables_paging_and_uses_only_approved_command(platform):
    _records, channel, _now = run_collection(platform)
    case = CASES[platform]

    assert channel.sent == [
        b"\n",
        f"{case['paging']}\n".encode(),
        f"{case['command']}\n".encode(),
    ]


@pytest.mark.parametrize("platform", CASES)
def test_every_platform_normalizes_status_and_descriptions_with_spaces(platform):
    records, _channel, now = run_collection(platform)

    first = records[0]
    assert first.device_name == "edge-01"
    assert first.device_ip == "192.0.2.10"
    assert first.platform == platform
    assert " " in first.port_description
    assert first.oper_status in {"up", "down"}
    assert first.collection_time == now
    if platform == "ubiquiti_edgeswitch":
        assert first.admin_status == ""
    else:
        assert first.admin_status == "up"


@pytest.mark.parametrize("platform", CASES)
def test_every_platform_uses_prompt_hostname_when_name_is_omitted(platform):
    records, _channel, _now = run_collection(platform, device_name=None)

    expected = "xr" if platform == "cisco_xr" else CASES[platform]["prompt"][:-1]
    if platform == "huawei_vrp":
        expected = "NE05E"
    elif platform == "ubiquiti_edgeswitch":
        expected = "C-HAWTH-382GLEN-BAS1"
    assert records[0].device_name == expected


@pytest.mark.parametrize("prompt", ["branch-router#", "branch-router>"])
def test_ios_and_ios_xe_hostname_extraction(prompt):
    assert extract_ios_hostname(prompt) == "branch-router"


def test_ios_xr_hostname_extraction():
    assert extract_ios_xr_hostname("RP/0/RSP0/CPU0:core-xr-01#") == "core-xr-01"


def test_ios_xr_parser_ignores_device_timestamp_before_interface_table():
    records = parse_ios_xr_interfaces_description(
        "Sun Sep 20 20:15:28.579 AEST\n"
        "Interface          Status      Protocol    Description\n"
        "Gi0/0/0/0          up          up          Core link north"
    )

    assert records[0].port_name == "Gi0/0/0/0"
    assert records[0].port_description == "Core link north"


def test_ios_parser_remains_strict_about_ios_xr_timestamp():
    with pytest.raises(ValueError, match="unrecognized Cisco interface row"):
        parse_interfaces_description(
            "Sun Sep 20 20:15:28.579 AEST\n"
            "Interface          Status      Protocol    Description\n"
            "Gi0/0/0/0          up          up          Core link north"
        )


def test_ios_xr_parser_remains_strict_after_interface_table_starts():
    with pytest.raises(ValueError, match="unrecognized Cisco interface row"):
        parse_ios_xr_interfaces_description(
            "Interface          Status      Protocol    Description\n"
            "Sun Sep 20 20:15:28.579 AEST"
        )


@pytest.mark.parametrize("prompt", ["<NE05E-01>", "[NE05E-01]"])
def test_huawei_hostname_extraction(prompt):
    assert extract_huawei_hostname(prompt) == "NE05E-01"


@pytest.mark.parametrize(
    "prompt", ["edge-switch-01#", "edge-switch-01>", "(C-HAWTH-382GLEN-BAS1) #"]
)
def test_edgeswitch_hostname_extraction(prompt):
    expected = "C-HAWTH-382GLEN-BAS1" if prompt.startswith("(") else "edge-switch-01"
    assert extract_edgeswitch_hostname(prompt) == expected


def test_edgeswitch_parses_exact_live_multiline_status_table():
    records = parse_interfaces_status(CASES["ubiquiti_edgeswitch"]["output"])

    assert [
        (
            record.port_name,
            record.port_description,
            record.admin_status,
            record.oper_status,
        )
        for record in records
    ] == [
        ("0/1", "Unit 1", "", "up"),
        ("0/2", "Unit 2", "", "up"),
        ("0/3", "Unit 6", "", "down"),
        ("0/7", "Access_port", "", "down"),
        ("0/13", "Access_port", "", "up"),
        ("0/17", "", "", "down"),
        ("3/1", "", "", "down"),
        ("3/2", "", "", "down"),
    ]


def test_edgeswitch_rejects_unexpected_non_table_content():
    with pytest.raises(ValueError, match="unrecognized EdgeSwitch interface row"):
        parse_interfaces_status(
            CASES["ubiquiti_edgeswitch"]["output"].replace(
                "Flow Control:Disabled", "unexpected footer"
            )
        )


@pytest.mark.parametrize("platform", CASES)
def test_every_platform_returns_no_records_for_empty_command_output(platform):
    records, _channel, _now = run_collection(platform, output="")
    assert records == []


@pytest.mark.parametrize("platform", CASES)
def test_every_platform_reports_parser_failure(platform):
    with pytest.raises(InterfaceCapabilityError, match="interface collection failed"):
        run_collection(platform, output="this is not a valid interface table")


@pytest.mark.parametrize("platform", CASES)
def test_every_platform_reports_rejected_session_setup(platform):
    case = CASES[platform]
    prompt = case["prompt"]
    paging = case["paging"]
    session, channel = make_session(
        [
            prompt.encode(),
            f"{paging}\r\n{case['rejection']}\r\n{prompt}".encode(),
        ]
    )

    with pytest.raises(
        InterfaceCapabilityError, match="rejected required session setup command"
    ):
        InterfaceService().collect(
            session,
            device_name="edge-01",
            device_ip="192.0.2.10",
            platform=platform,
        )
    assert channel.sent == [b"\n", f"{paging}\n".encode()]


@pytest.mark.parametrize("platform", CASES)
def test_every_platform_reports_rejected_collection_command_without_guessing(platform):
    case = CASES[platform]
    with pytest.raises(InterfaceCapabilityError, match="rejected approved command"):
        run_collection(platform, output=case["rejection"])


def test_unsupported_platform_is_a_clear_capability_error():
    session, _channel = make_session([])
    with pytest.raises(
        InterfaceCapabilityError, match="unsupported interface platform"
    ):
        InterfaceService().collect(
            session,
            device_name="device",
            device_ip="192.0.2.20",
            platform="generic",
        )


def test_huawei_phy_normalization_distinguishes_physical_and_admin_down():
    records = parse_interface_description(
        "Interface  PHY  Protocol  Description\n"
        "GE0/0/0    up   down      Protocol differs\n"
        "GE0/0/1    down up        Physical down\n"
        "GE0/0/2    *down up       Administratively down"
    )

    assert [(item.admin_status, item.oper_status) for item in records] == [
        ("up", "up"),
        ("up", "down"),
        ("down", "down"),
    ]


def test_huawei_parses_live_two_column_description_output_and_subinterfaces():
    records = parse_interface_description(
        "Interface                   Description\n"
        "Eth0/0/0                    HUAWEI, Ethernet0/0/0 Interface\n"
        "GE0/2/4                     Uplink AF60 to T-STKI-ASCEN-RTR1\n"
        "GE0/2/8.2434                SUPERLOOP1-PPPOE"
    )

    assert [item.port_name for item in records] == [
        "Eth0/0/0",
        "GE0/2/4",
        "GE0/2/8.2434",
    ]
    assert [item.port_description for item in records] == [
        "HUAWEI, Ethernet0/0/0 Interface",
        "Uplink AF60 to T-STKI-ASCEN-RTR1",
        "SUPERLOOP1-PPPOE",
    ]
    assert [(item.admin_status, item.oper_status) for item in records] == [
        ("", ""),
        ("", ""),
        ("", ""),
    ]


def test_huawei_two_column_collection_joins_approved_brief_status_by_name():
    description_output = (
        "Interface                   Description\r\n"
        "Eth0/0/0                    HUAWEI, Ethernet0/0/0 Interface\r\n"
        "GE0/2/4                     Uplink AF60 to T-STKI-ASCEN-RTR1\r\n"
        "GE0/2/8.2434                SUPERLOOP1-PPPOE\r\n"
        "Loop1                       Local loopback one\r\n"
        "Loop100                     Local loopback one hundred\r\n"
        "Loop828                     Local loopback eight twenty-eight\r\n"
        "Tun0/0/1                    Service tunnel\r\n"
        "Tunnel0/0/2                 Full-name tunnel\r\n"
        "NULL0                       Null interface\r\n"
        "Vlanif545                   Customer VLAN 545\r\n"
        "Vlanif745                   Customer VLAN 745"
    )
    brief_output = (
        "PHY: Physical\r\n"
        "*down: administratively down\r\n"
        "(l): loopback\r\n"
        "(s): spoofing\r\n"
        "(b): BFD down\r\n"
        "(B): Bit-error-detection down\r\n"
        "(e): ETHOAM down\r\n"
        "(d): Dampening Suppressed\r\n"
        "InUti/OutUti: input utility/output utility\r\n"
        "Interface                   PHY   Protocol InUti OutUti inErrors outErrors\r\n"
        "Ethernet0/0/0               up    up       0%    0%     0        0\r\n"
        "GigabitEthernet0/2/4        down  down     0%    0%     0        0\r\n"
        "GigabitEthernet0/2/8.2434   *down down     --    --     0        0\r\n"
        "LoopBack1                   up    up(s)    0%    0%     0        0\r\n"
        "LoopBack100                 up    up(s)    0%    0%     0        0\r\n"
        "LoopBack828                 up    up(s)    0%    0%     0        0\r\n"
        "Tunnel0/0/1                 up    up       0%    0%     0        0\r\n"
        "Tunnel0/0/2                 up    up       0%    0%     0        0\r\n"
        "NULL0                       up    up(s)    0%    0%     0        0\r\n"
        "Vlanif545                   up    up       0%    0%     0        0\r\n"
        "Vlanif745                   up    up       0%    0%     0        0"
    )
    prompt = CASES["huawei_vrp"]["prompt"]
    paging = CASES["huawei_vrp"]["paging"]
    description_command = CASES["huawei_vrp"]["command"]
    session, channel = make_session(
        [
            prompt.encode(),
            f"{paging}\r\n\r\n{prompt}".encode(),
            f"{description_command}\r\n{description_output}\r\n{prompt}".encode(),
            f"display interface brief\r\n{brief_output}\r\n{prompt}".encode(),
        ]
    )

    records = InterfaceService().collect(
        session, device_ip="192.0.2.10", platform="huawei_vrp"
    )

    assert [item.port_name for item in records] == [
        "Eth0/0/0",
        "GE0/2/4",
        "GE0/2/8.2434",
        "Loop1",
        "Loop100",
        "Loop828",
        "Tun0/0/1",
        "Tunnel0/0/2",
        "NULL0",
        "Vlanif545",
        "Vlanif745",
    ]
    assert [(item.admin_status, item.oper_status) for item in records] == [
        ("up", "up"),
        ("up", "down"),
        ("down", "down"),
        ("up", "up"),
        ("up", "up"),
        ("up", "up"),
        ("up", "up"),
        ("up", "up"),
        ("up", "up"),
        ("up", "up"),
        ("up", "up"),
    ]
    assert records[2].port_name == "GE0/2/8.2434"
    assert records[3].port_description == "Local loopback one"
    assert channel.sent == [
        b"\n",
        b"screen-length 0 temporary\n",
        b"display interface description\n",
        b"display interface brief\n",
    ]


def test_huawei_brief_parser_remains_strict_for_unexpected_rows():
    with pytest.raises(ValueError, match="unrecognized Huawei interface brief row"):
        parse_interface_brief(
            "Interface PHY Protocol InUti OutUti inErrors outErrors\n"
            "GE0/2/4 up up unexpected"
        )


def test_huawei_brief_accepts_spoofing_protocol_without_overriding_phy():
    statuses = parse_interface_brief(
        "PHY: Physical\n"
        "*down: administratively down\n"
        "(l): loopback\n"
        "(s): spoofing\n"
        "(b): BFD down\n"
        "(B): Bit-error-detection down\n"
        "(e): ETHOAM down\n"
        "(d): Dampening Suppressed\n"
        "InUti/OutUti: input utility/output utility\n"
        "Interface PHY Protocol InUti OutUti inErrors outErrors\n"
        "LoopBack1 up up(s) 0% 0% 0 0\n"
        "NULL0 up up(s) 0% 0% 0 0"
    )

    assert statuses["LoopBack1"] == ("up", "up")
    assert statuses["NULL0"] == ("up", "up")


def test_huawei_brief_rejects_unknown_pre_header_legend():
    with pytest.raises(ValueError, match="unrecognized Huawei interface brief row"):
        parse_interface_brief(
            "PHY: Physical\n"
            "(x): unexpected state\n"
            "Interface PHY Protocol InUti OutUti inErrors outErrors\n"
            "LoopBack1 up up(s) 0% 0% 0 0"
        )


def test_huawei_two_column_collection_requires_matching_brief_status():
    prompt = CASES["huawei_vrp"]["prompt"]
    paging = CASES["huawei_vrp"]["paging"]
    command = CASES["huawei_vrp"]["command"]
    session, _channel = make_session(
        [
            prompt.encode(),
            f"{paging}\r\n\r\n{prompt}".encode(),
            f"{command}\r\nInterface Description\r\nGE0/2/8.2434  SUPERLOOP1-PPPOE\r\n{prompt}".encode(),
            (
                "display interface brief\r\n"
                "Interface PHY Protocol InUti OutUti inErrors outErrors\r\n"
                "GigabitEthernet0/2/5 up up 0% 0% 0 0\r\n"
                f"{prompt}"
            ).encode(),
        ]
    )

    with pytest.raises(InterfaceCapabilityError, match="omitted description interface"):
        InterfaceService().collect(
            session, device_ip="192.0.2.10", platform="huawei_vrp"
        )


@pytest.mark.parametrize(
    "status", ["admin-down", "admin down", "administratively down"]
)
def test_cisco_xr_admin_down_spellings_normalize_to_down(status):
    records = parse_interfaces_description(
        "Interface  Status  Protocol  Description\n"
        f"Gi0/0/0/0  {status}  down      Maintenance"
    )

    assert records[0].admin_status == "down"
    assert records[0].oper_status == "down"
