"""Strict non-secret console profile and operator-controlled Teleport validation."""
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import platform
import subprocess
import tempfile
import tomllib

from orbitflow.config import ExecutionConfig

PROFILE = Path('data/sys_config/configuration-profile.toml')
ROUTING = ('proxy', 'cluster', 'bastion_host', 'bastion_user')
PATHS = {
    'devices': 'data/input/devices.xlsx',
    'templates': 'data/input/generated_template',
    'plans': 'outputs/reports/plan_configuration',
    'execution_reports': 'outputs/reports/configuration_execution',
    'inventory': 'data/inventory/inventory.json',
}


def validate(settings):
    """Reject unknown fields (including secrets and persisted concurrency)."""
    if not isinstance(settings, dict) or set(settings) != {'teleport', 'execution', 'paths'}:
        raise ValueError('Invalid profile sections')
    routing, execution, paths = (settings[k] for k in ('teleport', 'execution', 'paths'))
    if not all(isinstance(section, dict) for section in (routing, execution, paths)):
        raise ValueError('Invalid profile tables')
    if set(routing) - set((*ROUTING, 'teleport_key_path', 'teleport_cert_path')) or not all(routing.get(k) for k in ROUTING):
        raise ValueError('Invalid routing fields')
    if set(paths) != set(PATHS):
        raise ValueError('Invalid profile paths')
    if set(execution) != {'connection_start_interval', 'connection_retry_delay'}:
        raise ValueError('Invalid pacing fields')
    ExecutionConfig(**execution)
    for value in (*routing.values(), *paths.values()):
        if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError('Invalid profile value')
    for key in ROUTING:
        value = routing[key]
        if any(c.isspace() for c in value) or any(c in value for c in '/\\@?#') or value.startswith('-'):
            raise ValueError('Invalid routing value')
    return settings


def validate_paths(settings):
    """Probe configured destinations before connecting; never touch input content."""
    for key, value in settings['paths'].items():
        if key == 'devices':
            continue
        path = Path(value)
        directory = path.parent if key == 'inventory' else path
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=directory):
            pass
        if key == 'inventory' and path.exists():
            with path.open('rb'):
                pass


def load_profile(path=PROFILE):
    with Path(path).open('rb') as source:
        return validate(tomllib.load(source))


def save_profile(settings, path=PROFILE):
    """Atomically replace only a validated non-secret profile."""
    validate(settings)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for section, values in settings.items():
        lines.append(f'[{section}]')
        lines.extend(f'{k} = {json.dumps(v)}' for k, v in values.items())
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as destination:
            destination.write('\n'.join(lines) + '\n')
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def validate_session(settings, *, runner=subprocess.run, now=None):
    """Check active proxy/cluster/expiry without printing tsh output or logging in."""
    routing = settings['teleport']
    result = runner(['tsh', 'status', '--format=json'], capture_output=True, text=True, timeout=15, check=False)
    if result.returncode:
        raise ValueError('Run operator-controlled tsh login before continuing')
    active = json.loads(result.stdout).get('active') or {}
    expiry = datetime.fromisoformat(active.get('valid_until', '').replace('Z', '+00:00'))
    proxy = active.get('proxy_url', '').removeprefix('https://').rstrip('/')
    expected = routing['proxy'].removeprefix('https://').rstrip('/')
    if (expiry.tzinfo is None or expiry <= (now or datetime.now(timezone.utc))
            or proxy != expected or active.get('cluster') != routing['cluster']):
        raise ValueError('Teleport session expired or routing differs; run tsh login')
    for key in ('teleport_key_path', 'teleport_cert_path'):
        if platform.system() == 'Linux' and not routing.get(key):
            raise ValueError('Linux requires active Teleport identity file paths')
        if routing.get(key):
            with Path(routing[key]).open('rb'):
                pass
