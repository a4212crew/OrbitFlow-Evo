"""Offline read-only reconstruction from complete retained observation runs.

No transport or credential provider is invoked. Durable provenance is checked
under the spool lease before any plan/output is built. Legacy interpretation is
explicitly diagnostic and cannot enter confirmed execution.
"""
from datetime import datetime, timezone
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from orbitflow.configuration.plans import require
from orbitflow.result_spool import ResultSpool
from orbitflow.indexed_json import close_json_resources
from .catalogue import BY_ID
from .observation import bounded_observations, request_digest
from .planning import UNVERIFIED_SOURCE, plan, save
from .workbook import read_input, export_plan


def recover(workbook, spool_path, output, *, allow_unverified_legacy=False,
            max_evidence_age=3600, now=None):
    """Return a recovered BulkPlan and publish new JSON/XLSX, without networking.

    Bound runs require exact workbook/request digests and fresh successful
    evidence. Unbound legacy runs require explicit diagnostic opt-in; identity
    and evidence-age findings are preserved, and execution is prohibited.
    Complete outcomes (including failed targets) are required. Existing output
    files are never replaced. Observation and result working sets are disk-backed; individual safety limits still apply.
    """
    require(type(allow_unverified_legacy) is bool, 'invalid recovery mode')
    require(type(max_evidence_age) is int and 1 <= max_evidence_age <= 86400,
            'invalid evidence age')
    now = now or datetime.now(timezone.utc)
    require(now.tzinfo is not None, 'recovery time must be timezone-aware')
    output = Path(output)
    require(output.suffix == '.json', 'plan output must use .json')
    destination_book = output.with_suffix('.xlsx')
    require(not output.exists() and not destination_book.exists(), 'output already exists')
    requests = read_input(workbook)
    targets = list(dict.fromkeys(r['inputs']['management_ip'] for r in requests
                                if BY_ID[r['template_id']].family != 'All'))
    spool = ResultSpool(spool_path)
    with spool.indexed() as index:
        manifest = spool.manifest
        require(manifest.get('task') == 'configuration_observation_v2', 'wrong observation task')
        require(manifest.get('collection_complete') is True, 'incomplete observation collection')
        binding = manifest.get('binding')
        legacy = binding is None
        if legacy:
            require(allow_unverified_legacy, 'legacy provenance requires explicit diagnostic recovery')
        else:
            require(type(binding) is dict and binding == dict(
                request_digest=request_digest(requests), workbook_digest=requests.source_digest),
                'observation source binding mismatch')
        require(len(index) == len(targets), 'observation target count mismatch')
        for position, target in enumerate(targets, 1):
            record = index.get(position)
            require(record['target'] == target, 'observation target order mismatch')
            obs = record['payload']
            require(type(obs) is dict, 'invalid observation payload')
            require((record['status'] == 'failed' and obs == {'status': 'evidence_unavailable'})
                    or (record['status'] == 'success' and obs.get('status') == 'live_read_only'),
                    'observation outcome mismatch')
            if obs.get('status') == 'live_read_only':
                require(obs.get('identity', {}).get('management_ip') == target,
                        'observation identity mismatch')
                if not legacy:
                    try:
                        age = (now - datetime.fromisoformat(obs['observed_at'])).total_seconds()
                    except (KeyError, TypeError, ValueError):
                        require(False, 'evidence time unavailable')
                    require(0 <= age <= max_evidence_age, 'stale observation evidence')
        # Reuse the leased SQLite index; no recollection or manifest transition.
        observations = bounded_observations(spool)
        result = None
        try:
            source = (UNVERIFIED_SOURCE if legacy else 'workbook-sha256:') + requests.source_digest
            result = plan(requests, observations, source=source, now=now,
                          max_evidence_age=max_evidence_age)
            output.parent.mkdir(parents=True, exist_ok=True)
            # Finish both exports before publishing either. Exclusive hard links
            # prevent an output race from replacing another operator's artifacts.
            with TemporaryDirectory(prefix='.recovery-', dir=output.parent) as scratch:
                json_path = Path(scratch) / 'plan.json'
                book_path = Path(scratch) / 'plan.xlsx'
                save(result, json_path)
                export_plan(result, book_path)
                os.link(json_path, output)
                try:
                    os.link(book_path, destination_book)
                except BaseException:
                    output.unlink()
                    raise
        except BaseException:
            if result is not None:
                close_json_resources(result.view())
            raise
        finally:
            observations.close()

    return result
