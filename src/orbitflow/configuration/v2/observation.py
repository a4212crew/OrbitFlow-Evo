"""One shared read-only session per predefined target; sanitized spool persistence."""
from dataclasses import asdict
import re

from orbitflow.capabilities.interfaces import InterfaceService
from orbitflow.capabilities.vlans import VlanService
from orbitflow.compliance.methodology import resolve_methodologies
from orbitflow.compliance.resolvers import evidence, resolver_for
from orbitflow.compliance.vlan import safe_data
from orbitflow.configuration.plans import identity, require
from orbitflow.execution import execute_devices
from orbitflow.inventory import DeviceInventoryResolver, JsonInventoryStore
from orbitflow.logging import sanitize_text, module_logger
from orbitflow.result_spool import ResultSpool
from orbitflow.transport import connect_device
from orbitflow.vendors.common import DeviceCLI
from orbitflow.vendors.configuration_facts import _safe_source
from .catalogue import BY_ID


def snapshot(context, interfaces, vlans, *, clean=sanitize_text):
    """Project shared normalized observation and audit facts, never raw CLI."""
    require(vlans.configuration is not None, "configuration evidence unavailable")
    require(context.collection_status == "success", "identity evidence unavailable")
    factory = resolver_for(context)
    require(factory is not None, "unsupported audit family")
    resolver = factory(context, vlans, planning=True)
    resolver.resolve()
    # Compliance numeric sets are intentionally NOT used as planning limits.
    methods = resolve_methodologies(context, interfaces, vlans, clean=clean, planning=True)
    value = dict(identity=identity(context), observed_at=vlans.collection_time.isoformat(),
                 interfaces=[asdict(i) for i in interfaces],
                 vlans=[asdict(i) for i in vlans.interfaces], objects=[asdict(o) for o in vlans.objects],
                 facts=[asdict(n) for n in vlans.configuration], evidence=evidence(vlans.configuration),
                 audit=list(resolver.rows.values()), problems=resolver.problems, methodologies=methods,
                 status="live_read_only")
    # Datetime conversion happens before shared recursive sanitation.
    for interface in value["interfaces"]:
        interface["collection_time"] = interface["collection_time"].isoformat()
    return safe_data(value, lambda text: clean(_safe_source(text, context.platform)))


def collect(requests, credentials, transport_config, *, inventory_path="data/inventory/inventory.json",
            spool_root="outputs/runs/configuration_observation", execution_config=None, progress=None):
    """Credentials are an in-memory IP->DeviceCredentials map, never workbook data.

    Manual-only IPs are excluded before credential lookup or connection. Mixed
    manual/predefined targets are observed solely for their predefined requests.
    """
    from .planning import MAX_ROWS, request
    require(0 < len(requests) <= MAX_ROWS, "invalid observation request count")
    for r in requests:
        require(request(**r) == r, "invalid observation request")
    ips = list(dict.fromkeys(r["inputs"]["management_ip"] for r in requests
                            if BY_ID[r["template_id"]].family != "All"))
    secrets = [v for ip in ips if ip in credentials for v in
               (credentials[ip].username, credentials[ip].password, credentials[ip].secret) if v]
    pattern = re.compile("|".join(re.escape(v) for v in sorted(set(secrets), key=len, reverse=True))) if secrets else None
    def clean(text):
        text = sanitize_text(text)
        return pattern.sub("[REDACTED]", text) if pattern else text
    spool = ResultSpool.create(spool_root, "configuration_observation_v2", len(ips), clean=clean)
    store = JsonInventoryStore(inventory_path)

    def event(stage, ip="-", category="-", identity="-"):
        message = clean(f"{ip}: {stage}; identity={identity}")
        log = logger.error if category != "-" else logger.info
        log(message + f"; run_id={spool.path.name}",
            extra={"management_ip": ip, "error_category": category})
        if progress:
            progress(message + (f" ({category})" if category != "-" else ""))

    def worker(ip):
        event("connect", ip)
        require(ip in credentials, "target credentials unavailable or ambiguous")
        with connect_device(ip, credentials[ip], transport_config) as session:
            with DeviceCLI(session) as cli:
                event("identify", ip)
                context = DeviceInventoryResolver(store, sanitize_fact=clean).resolve(session, management_ip=ip, cli=cli)
                event("interface collection", ip, identity=context.device_id)
                interfaces = InterfaceService().collect(session, context, cli=cli)
                event("VLAN/config collection", ip, identity=context.device_id)
                vlans = VlanService().collect(session, context, cli=cli)
                event("audit/snapshot", ip, identity=context.device_id)
                return snapshot(context, interfaces, vlans, clean=clean)

    def persist(outcome):
        ip = ips[outcome.position - 1]
        payload = outcome.value if not outcome.error_category else dict(status="evidence_unavailable")
        spool.append(outcome, target=ip, payload=payload, failed=bool(outcome.error_category))
        counts[bool(outcome.error_category)] += 1
        event("failed" if outcome.error_category else "completed", ip,
              category="EvidenceCollectionError" if outcome.error_category else "-",
              identity=payload.get("identity", {}).get("inventory_id", "-"))

    counts = [0, 0]
    with module_logger("configuration", "bulk_planning") as (logger, _):
        event(f"run start; targets={len(ips)}; run_id={spool.path.name}; spool={spool.path}")
        try:
            with spool.collection():
                execute_devices(ips, worker, config=execution_config, on_outcome=persist)
        except Exception:
            event("run failed", category="ObservationRunError")
            raise
        finally:
            event(f"run end; completed={counts[0]}; failed={counts[1]}; run_id={spool.path.name}")
    return spool


def observations(spool):
    """Stream persisted observations; consumers can plan one target at a time."""
    for record in spool.records():
        yield record["target"], record["payload"]


def bounded_observations(spool):
    """Bound the adapter's immutable artifact size; the shared spool remains recoverable.

    Large API consumers can use observations() to plan/export one device at a
    time instead. No worker accumulates results or writes shared artifacts.
    """
    from .planning import MAX_CONTENT
    from orbitflow.configuration.plans import canonical
    result, size = {}, 0
    for ip, payload in observations(spool):
        size += len(canonical(payload).encode())
        require(size <= MAX_CONTENT // 2, "observation bundle too large; plan devices in smaller batches")
        result[ip] = payload
    return result
