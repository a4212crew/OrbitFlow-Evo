---
name: jumphost-connectivity
description: Use for OrbitFlow device connectivity through Teleport, jumphost/bastion access, Windows or Linux transport, Paramiko session establishment, direct-tcpip channels, tsh handling, prompt-aware network CLI sessions, or transport cleanup.
---

# Jumphost Connectivity

## Use This Skill When

Use this skill for:
- Teleport connectivity;
- `tsh` invocation;
- bastion/jumphost access;
- Windows transport changes;
- Linux/Ubuntu transport changes;
- Paramiko transport/session handling;
- `direct-tcpip`;
- transport cleanup;
- network CLI session establishment.

Do not use this skill for interface parsing only, Excel-only changes, or vendor configuration generation with no transport impact.

## Adjacent Capability Boundaries — Do Not Load by Default

Load another skill only when the task modifies that layer or targeted source inspection shows the transport change crosses into it.

- `../excel-inventory/SKILL.md` — device-input semantics.
- `../interface-collector/SKILL.md` — interface collection behaviour.
- `../access-vlan-provisioning/SKILL.md` — provisioning workflow behaviour.
- vendor CLI skills — paging/configuration/verification semantics.

## Architecture Rule

All device connectivity must pass through the OrbitFlow transport layer.

Higher-level workflows must not create independent SSH/jumphost paths.

The validated Windows and Linux transport implementations are intentionally different.

## Teleport Environment

Current validated environment:
- Teleport proxy: `teleport.lynhamnetworks.au:443`
- Cluster: `lynhamcluster`
- Bastion: `bastion-lyn-dc1-vic`
- Bastion login: `lightningadmin`

Do not store real passwords, OTPs, private keys, or device secrets in this file.

## Authentication Model

### Teleport
Teleport authentication remains interactive and is performed before automation starts.

Validate with:

```bash
tsh status
```

If the session is expired, the operator performs the approved `tsh login`.

Do not automate Teleport OTP entry.

### Network Device
Network-device authentication is separate from Teleport authentication.

The final device SSH session uses the network-device credential provider approved by the project.

## Windows Transport — Validated Pattern

Native Windows previously failed with Paramiko `ProxyCommand` due to subprocess-pipe/socket handling.

Use the validated local TCP forwarding method:

```text
Python on Windows
  -> tsh ssh -N -L 127.0.0.1:<local_port>:<device_ip>:22
  -> Teleport
  -> bastion-lyn-dc1-vic
  -> target device TCP/22
  -> Paramiko connects to 127.0.0.1:<local_port>
```

Operational sequence:
1. Detect Windows.
2. Locate `tsh` using PATH.
3. Start `tsh ssh -N -L`.
4. Retry opening the local-forward socket until it connects or the configured
   timeout expires; fail immediately if `tsh` exits.
5. Pass that same connected socket directly to Paramiko using target-device
   credentials. Do not read the SSH banner or discard a readiness connection.
6. Open the interactive network CLI.
7. Run task logic.
8. Close Paramiko.
9. Terminate the `tsh` subprocess in cleanup/finally logic.

Do not replace this with Paramiko `ProxyCommand` on Windows unless a future task explicitly revalidates the architecture.

## Linux / Ubuntu Transport — Validated Pattern

Validated on Ubuntu 26.04.1 LTS with Python 3.14.x and Teleport 18.7.x.

Use:

```text
Python on Linux
  -> Paramiko ProxyCommand
  -> tsh proxy ssh
  -> Teleport
  -> bastion
  -> Teleport SSH private key + certificate authentication
  -> bastion Paramiko transport
  -> direct-tcpip channel to <device_ip>:22
  -> second Paramiko SSHClient over that channel
  -> target device
```

Conceptual proxy command:

```bash
tsh proxy ssh \
  --cluster=lynhamcluster \
  --proxy=teleport.lynhamnetworks.au:443 \
  lightningadmin@bastion-lyn-dc1-vic:3022
```

### Teleport Key and Certificate

The Linux Paramiko bastion session must present both the Teleport private key and the Teleport SSH certificate.

Do not assume the private key alone is sufficient.

Prefer discovering the active Teleport profile/key paths rather than hardcoding user-specific home paths.

Validated Paramiko concept:

```python
private_key = paramiko.PKey.from_path(teleport_key_path)
private_key.load_certificate(teleport_cert_path)
```

Authenticate the bastion Paramiko session with `pkey=private_key` and the `ProxyCommand` socket.

### Second Hop

After the bastion session is established:

```python
bastion_transport = bastion_client.get_transport()

channel = bastion_transport.open_channel(
    kind="direct-tcpip",
    dest_addr=(device_ip, 22),
    src_addr=("127.0.0.1", 0),
)
```

Open a second Paramiko `SSHClient` to the target using `sock=channel` and the network-device credentials.

## Common Network CLI Behaviour

Once the final device SSH session is established, transport-specific logic should end.

Common flow:
1. `invoke_shell()`;
2. clear stale receive data;
3. send newline;
4. dynamically detect prompt;
5. disable paging using vendor-specific behaviour;
6. run commands with prompt-aware reads;
7. clean echoed command and trailing prompt;
8. close all resources.

Prompt detection must not hardcode hostnames.

The validated baseline recognizes Cisco-style prompts ending in `#` or `>`.

## Cleanup Rules

Always clean up all opened resources, including failure paths.

### Windows
- close final device client;
- terminate/kill the `tsh` tunnel process if still running.

### Linux
Close in reverse dependency order where practical:
- target device client;
- `direct-tcpip` channel;
- bastion client;
- Paramiko proxy object.

## Transport Abstraction Goal

Higher-level modules should call a common transport interface rather than branching by OS throughout the codebase.

Preferred conceptual shape:

```python
session = connect_device(device)
```

The exact return type may evolve, but collector/provisioning code should not know Teleport implementation details.

## Safety and Change Rules

- Do not bypass Teleport.
- Do not bypass the approved bastion.
- Do not automate OTP entry.
- Do not expose Teleport key material.
- Do not log device passwords.
- Do not redesign the validated transport path unless explicitly requested.
- Test Windows and Linux whenever transport behaviour changes.
