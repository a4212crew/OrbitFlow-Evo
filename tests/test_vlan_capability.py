from datetime import datetime, timezone

import pytest

from orbitflow.capabilities import VlanCapabilityError, VlanService
from orbitflow.models import InterfaceVlanObservation
from orbitflow.transport import DeviceSession
from orbitflow.vendors.cisco.vlans import (
    parse_ios_running_config,
    parse_ios_xr_running_config,
)
from orbitflow.vendors.huawei.vlans import parse_huawei_config
from orbitflow.vendors.ubiquiti.vlans import parse_edgeswitch_config
from orbitflow.vendors.vlan_types import parse_vlan_list


class FakeChannel:
    def close(self):
        self.closed = True

    def __init__(self, responses):
        self.responses, self.sent = iter(responses), []

    def sendall(self, data):
        self.sent.append(data)

    def settimeout(self, _timeout):
        pass

    def recv(self, _size):
        return next(self.responses)


def session_for(prompt, paging, command, output):
    channel = FakeChannel(
        [
            prompt.encode(),
            f"{paging}\r\n\r\n{prompt}".encode(),
            f"{command}\r\n{output}\r\n{prompt}".encode(),
        ]
    )

    class Client:
        def invoke_shell(self, **_kwargs):
            return channel

    return DeviceSession(Client(), lambda: None), channel


@pytest.mark.parametrize(
    ("text", "range_word", "expected"),
    [
        ("1,3-5 9", "-", (1, 3, 4, 5, 9)),
        ("545 745 to 747", "to", (545, 745, 746, 747)),
        ("10,10,11", "-", (10, 11)),
    ],
)
def test_vlan_list_and_range_parsing(text, range_word, expected):
    assert parse_vlan_list(text, range_word=range_word) == expected


@pytest.mark.parametrize("value", ["0", "4095", "20-10", "1,bad"])
def test_vlan_list_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        parse_vlan_list(value)


def test_ios_database_access_and_optional_trunk_fields():
    interfaces, objects = parse_ios_running_config("""vlan 445
 name CUSTOMER
!
interface GigabitEthernet1/0/1
 description Access customer
 switchport access vlan 445
 switchport mode access
!
interface GigabitEthernet1/0/2
 switchport trunk native vlan 99
 switchport trunk allowed vlan 100,200-202
 switchport mode trunk
!""")
    assert objects[0].vlan_ids == (445,)
    assert interfaces[0].access_vlan == 445
    assert interfaces[1].allowed_vlans == (100, 200, 201, 202)
    assert interfaces[1].native_vlan == 99


def test_ios_absent_allowed_list_remains_none():
    interfaces, _ = parse_ios_running_config(
        "interface Gi1/0/1\n switchport mode trunk\n!"
    )
    assert interfaces[0].allowed_vlans is None


def test_ios_ignores_non_numeric_vlan_global_commands():
    interfaces, objects = parse_ios_running_config(
        """vlan internal allocation policy ascending
!
vlan 100,200-202
!"""
    )
    assert interfaces == ()
    assert tuple(obj.object_id for obj in objects) == ("100", "200", "201", "202")


def test_ios_explicit_trunk_allowed_none_is_an_empty_vlan_set():
    interfaces, _ = parse_ios_running_config("""interface GigabitEthernet0/1
 switchport trunk allowed vlan none
 switchport mode trunk
!""")
    assert interfaces[0].allowed_vlans == ()
    assert interfaces[0].referenced_vlans == ()


@pytest.mark.parametrize(
    "bridge_domain_command",
    ["bridge-domain 746", "bridge-domain 746 split-horizon group 0"],
)
def test_ios_xe_evc_keeps_vlan_and_bridge_domain_separate(bridge_domain_command):
    interfaces, objects = parse_ios_running_config(
        f"""interface GigabitEthernet0/0/0
 service instance 44 ethernet
  encapsulation dot1q 445
  {bridge_domain_command}
!""",
        evc=True,
    )
    assert (interfaces[0].service_vlan, interfaces[0].service_binding_name) == (
        445,
        "746",
    )
    assert objects[-1].object_type == "bridge_domain"
    assert objects[-1].object_id == "746"
    assert objects[-1].name == "746"
    assert objects[-1].vlan_ids == ()


def test_ios_xr_does_not_infer_suffix_and_models_l2vpn_and_bvi():
    interfaces, objects = parse_ios_xr_running_config(
        """interface GigabitEthernet0/0/0/1.999 l2transport
 encapsulation dot1q 445
!
interface GigabitEthernet0/0/0/2.777
 encapsulation untagged
!
l2vpn
 bridge group METRO
  bridge-domain CUSTOMER-A
   interface GigabitEthernet0/0/0/1.999
   routed interface BVI44
!"""
    )
    tagged = next(x for x in interfaces if x.interface_name.endswith(".999"))
    untagged = next(x for x in interfaces if x.interface_name.endswith(".777"))
    assert tagged.service_vlan == 445
    assert tagged.service_binding_name == "METRO/CUSTOMER-A"
    assert untagged.service_vlan is None
    assert all(x.interface_name != "BVI44" for x in interfaces)
    assert objects[0].object_type == "bridge_domain"
    assert objects[0].object_id == "METRO/CUSTOMER-A"
    assert objects[0].vlan_ids == ()
    assert all(x.object_type != "vlan" for x in objects)


def test_ios_xr_bound_bvi_retains_interface_description_without_encapsulation():
    interfaces, _ = parse_ios_xr_running_config("""interface BVI2445
 description Routed customer gateway
 ipv4 address 192.0.2.1 255.255.255.0
!
l2vpn
 bridge group METRO
  bridge-domain CUSTOMER-A
   routed interface BVI2445
!""")

    assert len(interfaces) == 1
    assert interfaces[0].description == "Routed customer gateway"
    assert interfaces[0].port_type == "routed"
    assert interfaces[0].bridge_domains == ("CUSTOMER-A",)
    assert interfaces[0].tagged_vlans == ()
    assert interfaces[0].untagged_vlan == ""
    assert interfaces[0].referenced_vlans == ()
    assert interfaces[0].service_vlan is None


def test_ios_xr_l2vpn_bindings_respect_hierarchy_indentation():
    interfaces, objects = parse_ios_xr_running_config("""l2vpn
 bridge group GROUP-A
  bridge-domain DOMAIN-1
   interface Gi0/0/0/1.10
  bridge-domain DOMAIN-2
   interface Gi0/0/0/1.20
  interface OUTSIDE-BRIDGE-DOMAIN
 bridge group GROUP-B
  bridge-domain DOMAIN-1
   routed interface BVI30
!""")
    bindings = {item.interface_name: item.service_binding_name for item in interfaces}
    assert bindings == {}
    assert "OUTSIDE-BRIDGE-DOMAIN" not in bindings
    assert [item.object_id for item in objects] == [
        "GROUP-A/DOMAIN-1",
        "GROUP-A/DOMAIN-2",
        "GROUP-B/DOMAIN-1",
    ]


def test_ios_xr_preserves_outer_and_inner_vlan_identity():
    interfaces, _ = parse_ios_xr_running_config(
        "interface Gi0/0/0/1.10 l2transport\n"
        " encapsulation dot1q 100 second-dot1q 200\n!"
    )
    assert interfaces[0].outer_vlan == 100
    assert interfaces[0].inner_vlan == 200
    assert interfaces[0].referenced_vlans == (100, 200)


def test_huawei_database_switching_svi_dot1q_termination_and_vsi():
    interfaces, objects = parse_huawei_config("""vsi LBB-PPPOE-2445 static
#
vlan batch 545 745 to 746
#
interface GigabitEthernet0/0/1
 port link-type access
 port default vlan 545
#
interface GigabitEthernet0/0/2
 port link-type trunk
 port trunk allow-pass vlan 545 745 to 746
#
interface Vlanif545
#
interface GigabitEthernet0/0/3.445
 control-vid 44 dot1q-termination
 dot1q termination vid 445
 l2 binding vsi LBB-PPPOE-2445
#
interface GigabitEthernet0/0/4.1376
 vlan-type dot1q 1376
#""")
    assert [x.vlan_ids[0] for x in objects if x.object_type == "vlan"] == [
        545,
        745,
        746,
    ]
    assert interfaces[1].allowed_vlans == (545, 745, 746)
    service = interfaces[3]
    assert (
        service.service_vlan,
        service.service_binding_name,
        service.vlan_database_applicable,
    ) == (445, "LBB-PPPOE-2445", False)
    assert service.control_vlan == 44
    assert service.referenced_vlans == (44, 445)
    vsi = next(x for x in objects if x.object_type == "vsi")
    assert vsi.object_id == "LBB-PPPOE-2445"
    assert vsi.vlan_ids == ()
    assert interfaces[4].service_vlan == 1376


def test_edgeswitch_database_pvid_participation_exclusion_and_tagging():
    interfaces, objects = parse_edgeswitch_config("""vlan database
 vlan 445,545,745,1101,2400-2402
exit
interface 0/7
 description "Customer port"
 vlan pvid 445
 vlan participation include 445,1101
 vlan participation exclude 545
 vlan tagging 1101
exit""")
    assert objects[-1].vlan_ids == (2402,)
    port = interfaces[0]
    assert (port.pvid, port.untagged_vlans, port.tagged_vlans) == (445, (445,), (1101,))
    assert port.excluded_vlans == (545,)
    assert port.mode == "hybrid"


def test_edgeswitch_non_indented_exit_delimited_live_configuration():
    interfaces, objects = parse_edgeswitch_config("""vlan database
vlan 445,545,1101,2400-2402
vlan name 445 "Customer Access"
vlan name 1101 'Customer Transport'
exit
interface 0/7
description "Customer port"
vlan pvid 445
vlan participation include 445,1101
vlan participation exclude 545
vlan tagging 1101
exit
interface 0/8
description 'Trunk to POP'
vlan pvid 1
vlan participation include 1,445,545,1101
vlan tagging 1,445,545,1101
exit
interface lag 1
description "No VLAN configuration"
exit""")

    assert [(obj.object_id, obj.name) for obj in objects] == [
        ("445", "Customer Access"),
        ("545", "545"),
        ("1101", "Customer Transport"),
        ("2400", "2400"),
        ("2401", "2401"),
        ("2402", "2402"),
    ]
    assert [item.interface_name for item in interfaces] == ["0/7", "0/8"]
    assert interfaces[0].description == "Customer port"
    assert interfaces[0].mode == "hybrid"
    assert interfaces[0].excluded_vlans == (545,)
    assert interfaces[0].referenced_vlans == (445, 1101)
    assert interfaces[1].description == "Trunk to POP"
    assert interfaces[1].mode == "trunk"
    assert interfaces[1].tagged_vlans == (445, 545, 1101)


CASES = {
    "cisco_ios": ("ios#", "terminal length 0", "show running-config", "vlan 10\n!"),
    "cisco_xe": ("xe#", "terminal length 0", "show running-config", "vlan 10\n!"),
    "cisco_xr": (
        "RP/0/RSP0/CPU0:xr#",
        "terminal length 0",
        "show running-config",
        "interface Gi0/0/0/1.1\n encapsulation dot1q 10\n!",
    ),
    "huawei_vrp": (
        "<vrp>",
        "screen-length 0 temporary",
        "display current-configuration",
        "vlan batch 10\n#",
    ),
    "ubiquiti_edgeswitch": (
        "(edge) #",
        "terminal length 0",
        "show running-config",
        "vlan database\n vlan 10\nexit",
    ),
}


@pytest.mark.parametrize("platform", CASES)
def test_service_uses_only_approved_command_and_normalizes_identity(platform):
    prompt, paging, command, output = CASES[platform]
    session, channel = session_for(prompt, paging, command, output)
    now = datetime(2026, 9, 21, tzinfo=timezone.utc)
    state = VlanService(lambda: now).collect(
        session, device_ip="192.0.2.1", platform=platform
    )
    assert channel.sent == [b"\n", f"{paging}\n".encode(), f"{command}\n".encode()]
    assert state.device_ip == "192.0.2.1" and state.collection_time == now


def test_service_rejects_unsupported_platform():
    with pytest.raises(VlanCapabilityError, match="unsupported VLAN platform"):
        VlanService().collect(None, device_ip="192.0.2.1", platform="unknown")

@pytest.mark.parametrize('command,tags', [
    ('', 'ALL'), (' switchport trunk allowed vlan all\n', 'ALL'),
    (' switchport trunk allowed vlan none\n', 'NONE'),
    (' switchport trunk allowed vlan 100,200\n', (100, 200)),
])
def test_normalized_cisco_trunk_defaults_and_tag_states(command, tags):
    interfaces, objects = parse_ios_running_config(
        'interface Gi0/1\n switchport mode trunk\n' + command + '!')
    port = interfaces[0]
    assert port.port_type == 'trunk'
    assert port.untagged_vlan == ''
    assert port.tagged_vlans == tags
    assert 'untagged -> 1' not in port.service_mappings
    assert objects == ()


def test_evc_aggregation_preserves_exact_mappings_and_inner_detail():
    interfaces, objects = parse_ios_running_config('''vlan 500
!
interface Gi0/1
 service instance 1 ethernet
  encapsulation dot1q 100 second-dot1q 900
  bridge-domain 500
 service instance 2 ethernet
  encapsulation dot1q 200
  bridge-domain 600
 service instance 3 ethernet
  encapsulation untagged
  bridge-domain 700
!''', evc=True)
    assert len(interfaces) == 1
    port = interfaces[0]
    assert port.port_type == 'evc'
    assert port.untagged_vlan == '700'
    assert port.tagged_vlans == (100, 200)
    assert port.bridge_domains == ('500', '600', '700')
    assert port.service_mappings == ('100 -> 500', '200 -> 600', 'untagged -> 700')
    assert port.service_details[0].inner_vlan == 900
    assert {(o.object_type, o.object_id) for o in objects} == {
        ('vlan', '500'), ('bridge_domain', '500'), ('bridge_domain', '600'), ('bridge_domain', '700')}


@pytest.mark.parametrize('parser,terminator,evidence', [
    (parse_ios_running_config, '!', 'no switchport'),
    (parse_ios_running_config, '!', 'ip address 192.0.2.1 255.255.255.0'),
    (parse_ios_running_config, '!', 'ipv6 address 2001:db8::1/64'),
    (parse_huawei_config, '#', 'undo portswitch'),
    (parse_huawei_config, '#', 'ip address 192.0.2.1 255.255.255.0'),
    (parse_huawei_config, '#', 'ipv6 address 2001:db8::1/64'),
])
def test_physical_routed_interface_requires_positive_evidence(parser, terminator, evidence):
    interfaces, objects = parser(
        f'interface GigabitEthernet0/1\n {evidence}\n{terminator}\n'
        f'interface GigabitEthernet0/2\n description spare\n{terminator}\n'
    )
    assert len(interfaces) == 1
    assert interfaces[0].interface_name == 'GigabitEthernet0/1'
    assert interfaces[0].port_type == 'routed'
    assert interfaces[0].tagged_vlans == ()
    assert interfaces[0].bridge_domains == ()
    assert objects == ()


def test_ios_routed_physical_subinterface_and_svi():
    interfaces, objects = parse_ios_running_config('''interface Gi0/1
 no switchport
!
interface Gi0/1.860
 encapsulation dot1Q 860
!
interface Vlan100
 ip address 192.0.2.1 255.255.255.0
!''')
    assert [p.port_type for p in interfaces] == ['routed'] * 3
    assert interfaces[0].tagged_vlans == ()
    assert interfaces[1].service_mappings == ('860 -> routed',)
    assert interfaces[1].bridge_domains == ()
    assert interfaces[2].bridge_domains == ('100',)
    assert interfaces[2].untagged_vlan == ''
    assert interfaces[2].tagged_vlans == ()
    assert objects == ()


def test_xr_real_interfaces_canonical_bindings_and_database_hierarchy():
    interfaces, objects = parse_ios_xr_running_config('''l2vpn
 bridge group BG
  bridge-domain RSVD-RSP0
   interface Te0/0/0/18.2400
   interface Te0/0/0/18.9999
   routed interface BVI100
!
interface TenGigE0/0/0/18.2400 l2transport
 encapsulation dot1q 2400 second-dot1q 123
!
interface TenGigE0/0/0/18.860
 encapsulation dot1q 860
!
interface BVI100
!
interface Loopback0
!''')
    assert len(interfaces) == 4
    assert interfaces[0].service_mappings == ('2400 -> RSVD-RSP0',)
    assert interfaces[0].tagged_vlans == (2400,)
    assert interfaces[1].service_mappings == ('860 -> routed',)
    assert interfaces[1].bridge_domains == ()
    assert interfaces[2].port_type == 'routed'
    assert interfaces[2].bridge_domains == ('RSVD-RSP0',)
    assert interfaces[2].tagged_vlans == ()
    assert interfaces[3].port_type == 'routed'
    assert [(o.object_type, o.object_id, o.domain_id, o.name) for o in objects] == [
        ('bridge_domain', 'BG/RSVD-RSP0', 'RSVD-RSP0', 'RSVD-RSP0')]


def test_huawei_database_objects_require_declarations_and_routed_termination():
    interfaces, objects = parse_huawei_config('''vsi DECLARED static
#
vlan 100
 description USERS
#
interface GE0/1.100
 dot1q termination vid 100
 l2 binding vsi MISSING
#
interface GE0/1.200
 dot1q termination vid 200
 ip address 192.0.2.1 255.255.255.0
#
interface Vlanif300
#
interface GE0/2
 port default vlan 10
 port trunk allow-pass vlan 20 30
#
interface GE0/3
 ip address 192.0.2.2 255.255.255.0
#''')
    assert {(o.object_type, o.domain_id, o.name) for o in objects} == {
        ('vlan', '100', 'USERS'), ('vsi', 'DECLARED', 'DECLARED')}
    assert interfaces[0].service_mappings == ('100 -> MISSING',)
    assert interfaces[1].port_type == 'routed'
    assert interfaces[1].service_mappings == ('200 -> routed',)
    assert interfaces[2].bridge_domains == ('300',)
    assert interfaces[2].tagged_vlans == ()
    assert interfaces[3].port_type == 'hybrid'
    assert interfaces[3].service_mappings == ('untagged -> 10', '20 -> 20', '30 -> 30')
    assert interfaces[4].port_type == 'routed'


def test_edgeswitch_active_membership_and_database_independence():
    interfaces, objects = parse_edgeswitch_config('''interface 0/1
 vlan pvid 100
 vlan participation include 100,200,300
 vlan participation exclude 300
 vlan tagging 200,300
exit
interface 0/2
 vlan pvid 100
 vlan participation include 100,200
 vlan tagging 100,200
exit
interface 0/3
 vlan pvid 100
 vlan participation exclude 100
exit''')
    assert interfaces[0].port_type == 'hybrid'
    assert interfaces[0].bridge_domains == ('100', '200')
    assert interfaces[0].tagged_vlans == (200,)
    assert interfaces[1].port_type == 'trunk'
    assert interfaces[1].untagged_vlan == ''
    assert interfaces[2].bridge_domains == ()
    assert interfaces[2].untagged_vlan == ''
    assert objects == ()

@pytest.mark.parametrize('prefix', ['trunk', 'hybrid'])
def test_huawei_pvid_with_tagged_membership(prefix):
    tagged_command = 'port trunk allow-pass vlan' if prefix == 'trunk' else 'port hybrid tagged vlan'
    ports, _ = parse_huawei_config(
        f'interface GE0/1\n port {prefix} pvid vlan 10\n {tagged_command} 20 30\n#')
    assert ports[0].port_type == 'hybrid'
    assert ports[0].untagged_vlan == '10'
    assert ports[0].tagged_vlans == (20, 30)
    assert ports[0].service_mappings == ('untagged -> 10', '20 -> 20', '30 -> 30')

@pytest.mark.parametrize('global_first', [True, False])
@pytest.mark.parametrize('vlan_database', [True, False])
@pytest.mark.parametrize('member_suffix', ['', ' split-horizon group 0'])
def test_global_evc_membership_overrides_switchport_defaults(global_first, vlan_database, member_suffix):
    global_config = f'''bridge-domain 13
 member Gi0/13 service-instance 13
!
bridge-domain 746
 member GigabitEthernet0/13 service-instance 746{member_suffix}
 member GigabitEthernet0/99 service-instance 999
!
'''
    local_config = '''interface GigabitEthernet0/13
 switchport mode trunk
 switchport trunk allowed vlan 1,100
 service instance 13 ethernet
  encapsulation untagged
 service instance 746 ethernet
  encapsulation dot1q 746
!
'''
    ports, objects = parse_ios_running_config(
        global_config + local_config if global_first else local_config + global_config,
        evc=True, vlan_database=vlan_database)
    assert len(ports) == 1
    port = ports[0]
    assert port.interface_name == 'GigabitEthernet0/13'
    assert port.port_type == 'evc'
    assert port.untagged_vlan == '13'
    assert port.tagged_vlans == (746,)
    assert port.bridge_domains == ('13', '746')
    assert port.service_mappings == ('untagged -> 13', '746 -> 746')
    assert {(o.object_type, o.domain_id) for o in objects} == {
        ('bridge_domain', '13'), ('bridge_domain', '746')}


@pytest.mark.parametrize('parser,config,options', [
    (parse_ios_running_config, '''vlan 1,10
!
interface Gi0/1
 switchport mode trunk
 switchport trunk native vlan 1
 switchport trunk allowed vlan 1,10
!''', {}),
    (parse_ios_running_config, '''bridge-domain 1
 member Gi0/1 service-instance 1
!
interface Gi0/1
 service instance 1 ethernet
  encapsulation untagged
 service instance 10 ethernet
  encapsulation dot1q 10
  bridge-domain 10
!''', {'evc': True}),
    (parse_ios_xr_running_config, '''l2vpn
 bridge group BG
  bridge-domain 1
   interface Gi0/1.1
  bridge-domain 10
   interface Gi0/1.10
!
interface Gi0/1.1 l2transport
 encapsulation dot1q 1
!
interface Gi0/1.10 l2transport
 encapsulation dot1q 10
!''', {}),
    (parse_huawei_config, '''vlan batch 1 10
#
interface GE0/1
 port trunk pvid vlan 1
 port trunk allow-pass vlan 1 10
#''', {}),
    (parse_edgeswitch_config, '''vlan database
 vlan 1,10
exit
interface 0/1
 vlan pvid 1
 vlan participation include 1,10
 vlan tagging 10
exit''', {}),
])
def test_vlan_one_suppression_across_normalized_vendors(parser, config, options):
    ports, objects = parser(config, **options)
    assert ports
    for port in ports:
        assert port.untagged_vlan == ''
        assert 1 not in port.tagged_vlans
        assert '1' not in port.bridge_domains
        assert all('1' not in mapping.split(' -> ') for mapping in port.service_mappings)
    assert any(10 in p.tagged_vlans for p in ports)
    assert any('10 -> 10' in p.service_mappings for p in ports)
    assert {o.domain_id for o in objects} == {'10'}
