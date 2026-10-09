"""Issue 85: saved relationships refine review, never compliance policy."""
import hashlib
import json
from pathlib import Path

import pytest

from orbitflow.compliance import evaluate_vlan_compliance
from orbitflow.compliance.methodology import resolve_methodologies
from test_methodology_resolution import resolve, snapshot
from test_vlan_compliance import POLICY


XR = ('interface TenGigE0/0/0/1\n!\n'
      'interface TenGigE0/0/0/1.999 l2transport\n encapsulation untagged\n!\n'
      'interface BVI445\n!\nl2vpn\n bridge group G\n  bridge-domain named\n'
      '   interface TenGigE0/0/0/1.999\n   routed interface BVI445')
EVC = ('vlan 445\n!\ninterface Gi0/1\n shutdown\n switchport mode trunk\n'
       ' switchport trunk allowed vlan none\n service instance 7 ethernet\n'
       '  encapsulation dot1q 3999\n')
PW = ('pseudowire-class CORE\n encapsulation mpls\n!\n'
      'interface pseudowire7\n encapsulation mpls\n neighbor 192.0.2.1 77\n pw-class CORE')
CASES = [(family, PW) for family in ('C3750X', 'C3850', 'ME3600X', 'ASR920', 'NCS540')]
CASES += [('NCS540', XR), ('NCS540', XR.replace('routed interface BVI445', 'routed interface BVI999'))]
CASES += [(family, EVC + binding) for family in ('ASR920', 'ME3600X') for binding in (
    '  bridge-domain 445 split-horizon group 0',
    '!\nbridge-domain 445\n member Gi0/1 service-instance 7 split-horizon group 0',
    '  bridge-domain 445\n!\nbridge-domain 445\n member Gi0/1 service-instance 7',
    '!\nbridge-domain 445\n member Gi0/9 service-instance 7 split-horizon group 0')]


@pytest.mark.parametrize('family,config', CASES)
def test_compliance_baseline_and_evidence(family, config):
    expected = json.loads((Path(__file__).parent / 'fixtures/methodology_relationships_compliance.json').read_text())
    ctx, state = snapshot(config, family)
    before = evaluate_vlan_compliance(ctx, [], state, POLICY)
    assert hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest() == expected[CASES.index((family, config))]
    rows = resolve_methodologies(ctx, [], state)
    assert evaluate_vlan_compliance(ctx, [], state, POLICY) == before
    for row in rows:
        for proof in row['evidence']:
            assert proof['source_filename'] == 'fixture.cfg'
            assert proof['excerpt'] == config.splitlines()[proof['line'] - 1]


@pytest.mark.parametrize('family', ['C3750X', 'C3850', 'ME3600X', 'ASR920', 'NCS540'])
def test_pseudowire_identity_and_scope(family):
    context = resolve('pseudowire-class CORE', family)
    assert len(context) == 1 and context[0]['configuration_classification'] == 'not_applicable'
    assert context[0]['config_interface_name'] == ''
    rows = resolve(PW, family, observed=['pseudowire7'])
    actual = [r for r in rows if r['config_interface_name']]
    assert len(actual) == 1
    assert actual[0]['config_interface_name'] == 'pseudowire7'
    assert actual[0]['interface_match_status'] == 'matched'
    assert all(r['configuration_classification'] == 'not_applicable' for r in rows)
    assert all(r['methodology'] == [] and not r['review_needed'] for r in rows)
    assert {p['line'] for r in rows for p in r['evidence']} == {1, 2, 4, 5, 6, 7}
    bad = resolve(PW + '\n encapsulation future-mode', family)
    assert any(r['review_needed'] for r in bad)


def test_xr_bvi_and_untagged_are_proven_without_numeric_inference():
    rows = resolve(XR, 'NCS540')
    assert len(rows) == 2
    assert all(r['configuration_classification'] == 'standard_configuration' for r in rows)
    child = next(r for r in rows if r['methodology'] == ['M04'])
    assert child['mapping']['outer_vlan'] == child['mapping']['audit_vlan'] == []
    assert child['mapping']['bridge_domains'] == [['G', 'named']]
    bvi = next(r for r in rows if r['config_interface_name'] == 'BVI445')
    assert bvi['record_kind'] == 'service_context' and bvi['methodology'] == []


@pytest.mark.parametrize('config,code,excerpt', [
    (XR.replace('routed interface BVI445', 'routed interface BVI999'),
     'MISSING_BRIDGE_DOMAIN_INTERFACE_REFERENCE', '   routed interface BVI999'),
    (XR.replace('routed interface BVI445', 'interface BVI445'),
     'NON_L2TRANSPORT_BRIDGE_DOMAIN_ATTACHMENT', '   interface BVI445'),
    (XR.replace('   interface TenGigE0/0/0/1.999\n', ''),
     'UNBOUND_L2TRANSPORT_SUBINTERFACE', 'interface TenGigE0/0/0/1.999 l2transport'),
    (XR + '\n  bridge-domain other\n   interface TenGigE0/0/0/1.999',
     'CONFLICTING_BRIDGE_DOMAIN_ATTACHMENTS', '   interface TenGigE0/0/0/1.999'),
    (XR.replace('interface TenGigE0/0/0/1.999 l2transport', 'interface TenGigE0/0/0/1.999'),
     'NON_L2TRANSPORT_BRIDGE_DOMAIN_ATTACHMENT', '   interface TenGigE0/0/0/1.999'),
    (XR.replace('   interface TenGigE0/0/0/1.999', '   routed interface TenGigE0/0/0/1.999'),
     'INVALID_ROUTED_BRIDGE_DOMAIN_ATTACHMENT', '   routed interface TenGigE0/0/0/1.999'),
    (XR + '\n  bridge-domain other\n   routed interface BVI445',
     'CONFLICTING_BRIDGE_DOMAIN_ATTACHMENTS', '   routed interface BVI445'),
    (XR.replace('   interface TenGigE0/0/0/1.999', '   interface TenGigE0/0/0/1.888'),
     'MISSING_BRIDGE_DOMAIN_INTERFACE_REFERENCE', '   interface TenGigE0/0/0/1.888'),
])
def test_xr_unresolved_references_remain(config, code, excerpt):
    rows = resolve(config, 'NCS540')
    assert any(r['review_needed'] and code in {f['code'] for f in r['standard_findings']} for r in rows)
    assert any(p['excerpt'] == excerpt for r in rows if r['review_needed'] for p in r['evidence'])
    assert not any(r['config_interface_name'] == 'BVI999' for r in rows)


@pytest.mark.parametrize('family', ['ASR920', 'ME3600X'])
@pytest.mark.parametrize('binding', [
    '  bridge-domain 445', '  bridge-domain 445 split-horizon group 0',
    '!\nbridge-domain 445\n member GigabitEthernet0/1 service-instance 7',
    '!\nbridge-domain 445\n member Gi0/1 service-instance 7 split-horizon group 0',
    '  bridge-domain 445\n!\nbridge-domain 445\n member Gi0/1 service-instance 7 split-horizon group 2',
])
def test_valid_evc_bindings(family, binding):
    rows = resolve(EVC + binding, family)
    assert all(r['configuration_classification'] == 'standard_configuration' for r in rows)
    service = next(r for r in rows if r.get('service_instance_id') == '7')
    assert service['mapping']['binding_status'] == 'valid'
    assert service['mapping']['resolved_bridge_domain'] == ['445']
    assert service['mapping']['outer_vlan'] == [3999]


@pytest.mark.parametrize('family', ['ASR920', 'ME3600X'])
@pytest.mark.parametrize('binding,code', [
    ('', 'UNRESOLVED_SERVICE_INSTANCE'),
    ('!\nbridge-domain 445\n member Gi0/9 service-instance 7 split-horizon group 0', 'INVALID_BRIDGE_DOMAIN_MEMBER_REFERENCE'),
    ('!\nbridge-domain 445\n member Gi0/1 service-instance 8 split-horizon group 0', 'INVALID_BRIDGE_DOMAIN_MEMBER_REFERENCE'),
    ('  bridge-domain 545\n!\nbridge-domain 445\n member Gi0/1 service-instance 7 split-horizon group 0', 'CONFLICTING_BRIDGE_DOMAIN_BINDING'),
    ('!\nbridge-domain 445\n member Gi0/1 service-instance 7 split-horizon group nope', 'UNSUPPORTED_FORWARDING_SYNTAX'),
    ('  bridge-domain named', 'INVALID_EVC_BRIDGE_DOMAIN'),
])
def test_invalid_evc_bindings_including_shutdown(family, binding, code):
    rows = resolve(EVC + binding, family)
    assert any(r['review_needed'] and code in {f['code'] for f in r['standard_findings']} for r in rows)
    assert any(p['excerpt'] == ' shutdown' for r in rows for p in r['evidence'])


def test_asr_policy_range_does_not_invalidate_the_binding():
    rows = resolve(EVC + '  bridge-domain 4094', 'ASR920')
    assert all('INVALID_EVC_BRIDGE_DOMAIN' not in {f['code'] for f in r['standard_findings']} for r in rows)
    assert rows[0]['mapping']['binding_status'] == 'valid'
    assert rows[0]['mapping']['resolved_bridge_domain'] == ['4094']


def test_pseudowire_attachment_validation_is_out_of_scope():
    config = ('interface PW-Ether7 l2transport\n!\nl2vpn\n bridge group G\n'
              '  bridge-domain A\n   interface PW-Ether7\n'
              '  bridge-domain B\n   routed interface PW-Ether7')
    row = resolve(config, 'NCS540')[0]
    assert row['configuration_classification'] == 'not_applicable'
    assert not row['review_needed']
    assert row['mapping']['bridge_domains'] == [['G', 'A'], ['G', 'B']]
    assert 'CONFLICTING_BRIDGE_DOMAIN_ATTACHMENTS' in {f['code'] for f in row['configuration_findings']}
