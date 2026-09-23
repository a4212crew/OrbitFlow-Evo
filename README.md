# OrbitFlow

OrbitFlow is a multi-vendor network automation platform. This version provides
the shared SSH transport layer and a reusable Cisco IOS/IOS-XE interactive CLI;
inventory, collection, and provisioning workflows are intentionally out of scope.

## Setup

Use Python 3.11 or newer in a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate          # Linux
# .venv\Scripts\Activate.ps1       # Windows PowerShell
python -m pip install -r requirements.txt
export PYTHONPATH="$PWD/src"         # Linux
# $env:PYTHONPATH = "$PWD/src"       # Windows PowerShell
```

Install `tsh` separately and authenticate interactively before running OrbitFlow:

```bash
tsh login --proxy=<teleport-proxy>
tsh status
```

OrbitFlow never performs `tsh login` or handles an OTP.

## Transport API

Callers provide routing configuration and target-device credentials explicitly;
nothing contains production credentials or user-specific paths.

```python
from pathlib import Path
from orbitflow.transport import DeviceCredentials, TransportConfig, connect_device

config = TransportConfig(
    proxy="teleport.example.net:443",
    cluster="example-cluster",
    bastion_host="example-bastion",
    bastion_user="teleport-user",
    # Required on Linux; discover these from the active tsh profile.
    teleport_key_path=Path("/path/from/active/tsh/profile/key"),
    teleport_cert_path=Path("/path/from/active/tsh/profile/key-cert.pub"),
    verify_bastion_host_key=False,  # Linux bastion; permissive by default.
    verify_device_host_key=False,  # Target device; permissive by default.
)

with connect_device(
    "192.0.2.10",
    DeviceCredentials(username="network-user", password="from-secret-provider"),
    config,
) as session:
    shell = session.invoke_shell()
```

## Cisco IOS/IOS-XE interactive CLI

`CiscoIOSCLI` uses an existing `DeviceSession`; it does not implement or bypass
the transport layer. It dynamically recognizes prompts ending in `#` or `>`,
disables paging with `terminal length 0`, and reads until each command's trailing
prompt using the requested timeout. Returned text excludes the command echo and
trailing prompt.

```python
from orbitflow.vendors.cisco import CiscoIOSCLI

with connect_device(device_host, credentials, config) as session:
    cli = CiscoIOSCLI(session, timeout=10)
    version = cli.run_command("show version", timeout=30)
```

This class is specifically for IOS and IOS-XE. Future IOS-XR behavior belongs in
a separate vendor module rather than being inferred from matching commands.

On Windows, OrbitFlow starts `tsh ssh -N -L` and connects Paramiko to the local
forward while retaining the device address for SSH host-key verification. On
Linux, it starts `tsh proxy ssh`, authenticates the bastion using the
provided Teleport private key and certificate, opens a Paramiko `direct-tcpip`
channel, and connects the target client over that channel. Resources are closed
in reverse dependency order.

For the target-device session on either operating system, normal Paramiko
password authentication remains the first attempt. If it is rejected and the
server supports keyboard-interactive authentication, OrbitFlow retries using
the same `DeviceCredentials.password`. The handler answers only prompts whose
text identifies them as password prompts; it rejects unrelated challenges such
as OTP prompts. Teleport and bastion authentication are unchanged.

Host-key verification is independently configurable for the Linux bastion and
the target device. Both `verify_bastion_host_key` and
`verify_device_host_key` default to `False`, matching the permissive host-key
handling successfully used during Windows and Linux live validation. Permissive
mode uses Paramiko's `AutoAddPolicy` and does not persist learned keys. Setting
either applicable option to `True` loads normal system host keys and uses
Paramiko's `RejectPolicy`; strict mode therefore requires the relevant host key
to have been provisioned there. OrbitFlow does not load Teleport-specific
known-host files or implement custom Teleport CA verification. Permissive mode
trades protection against machine-in-the-middle attacks for compatibility, so
enable strict verification when trusted system host keys can be provisioned.

The caller is responsible for obtaining target credentials from an approved
secret provider and for discovering the active Teleport identity paths. Passwords,
private keys, and OTPs must not be logged or committed.

## Single-device interface live validation

`scripts/live_validate_interfaces.py` is a small integration utility for checking
the existing interface capability against one live device. It accepts existing
`DeviceCredentials` and `TransportConfig` objects, calls the shared transport and
`InterfaceService`, and prints only normalized interface fields. It does not read
inventory or implement a production collection workflow.

```python
from scripts.live_validate_interfaces import run_live_validation

records = run_live_validation(
    device_host,
    platform,
    credentials,
    transport_config,
    # device_name="edge-01",  # Optional compatibility override.
)
```

When `device_name` is omitted, the vendor adapter discovers the hostname from
the device's existing CLI prompt; no additional device command is sent.

Obtain credentials and configuration through the approved operator-side secret
and Teleport-profile mechanisms; do not place secret values in the script.

## Tests

The suite uses mocks and does not contact Teleport or network devices:

```bash
PYTHONPATH=src pytest
```


## Local ChatGPT-to-Codex orchestration

OrbitFlow-Evo can use GitHub Issues as the task queue while running Codex locally on either Windows or Linux.

Prerequisites:

```bash
gh auth status
codex --version
codex login
```

Bootstrap the labels once:

```bash
python scripts/orchestration/bootstrap.py
```

Run the controller continuously:

```bash
python scripts/orchestration/controller.py --watch
```

Preview the next queued task without mutating GitHub or Git state:

```bash
python scripts/orchestration/controller.py --dry-run
```

The controller polls for `codex-task` and `codex-revise`, creates one dedicated Git worktree/branch per issue, invokes the locally authenticated Codex CLI, runs the full deterministic pytest suite, and only commits/pushes/opens or updates the PR after tests pass. It then returns the issue to Atlas review.

The Python orchestration layer is intentionally cross-platform. Shared orchestration logic and tests must use platform-aware paths rather than hard-coded Windows or POSIX separators.

This path does **not** require `OPENAI_API_KEY`. Codex authentication is through the local ChatGPT login. Device/Teleport credentials must never be placed in task issues or Codex prompts.

See `docs/architecture/codex-orchestration.md` for the complete state machine, test gate, 15-iteration replan gate, and first-validation procedure.
