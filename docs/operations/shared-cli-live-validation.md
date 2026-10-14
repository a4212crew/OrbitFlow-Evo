# Shared CLI read-only live validation (Issue #97)

Owner-controlled hardware checks are pending. Do not use Codex to connect to
production devices or supply production credentials. No configuration apply,
write/save, or destructive commands belong to this matrix. Use the existing
operator workflows and one shared shell per target; keep raw configuration
captures private and outside version control.

| Stage | Device | Read-only checks | Required result |
| --- | --- | --- | --- |
| 1 | ME3600X | `show ethernet service instance id 2324 interface TenGigabitEthernet0/1 detail` | Complete scoped negative reply becomes `absent` with evidence, never `error`; note whether echo is full, wrapped or `$` clipped. |
| 1 | ASR920 | `show ethernet service instance id 1234 interface TenGigabitEthernet0/0/24 detail` | Same absence/evidence check. |
| 1 | Both EVC families | Owner-selected existing EFP lookup; planner v2 Templates 9-16 read-only observation | Present service facts/evidence and absent service outcomes agree with independent operator inspection; errors remain distinct. |
| 2 | C3750X / C3850 | Inventory identify/refresh, interface collection, VLAN observation/compliance, planner observation | Identity, interface/VLAN facts and compliance match independently reviewed configuration. |
| 2 | NCS540 IOS-XR | Inventory, interface/VLAN observation/compliance through supported workflows | XR prompts/location prefixes and service identities remain intact. |
| 2 | EdgeSwitch | Inventory, interface/VLAN collection/compliance and planner supported observation | Shell annotations, participation/tagging/PVID remain intact. |
| 2 | Huawei NE05E | Inventory, interface/VLAN observation/compliance | Huawei angle/view prompts, subinterfaces and VSI relationships remain intact. |
| Both | Every connected representative above, especially ME3600X/ASR920 | Configuration backup using existing backup workflow | Compare private capture against independent complete read-only configuration: line order, indentation, trailing spaces, blank lines, long lines, banners including prompt-shaped lines, first/last statements and `end`/vendor ending. Only CRLF/CR and ANSI framing normalization plus command echo/final prompt removal is allowed. Check large captures for truncation. |

Run stage 1 before expanding to stage 2. Record model/software, workflow,
completion/failure category, echo shape, and integrity comparison outcome without
credentials or raw secret-bearing output. Record unavailable devices as pending,
not passed. Repeat representative interface/VLAN collection after backup to
verify subsequent command synchronization on the same workflow shell where
supported. A command timeout/channel closure must prevent another command on that
shell; use a fresh operator-owned session for recovery.

Deterministic tests cover split reads and mismatches. Hardware timing, terminal
width behavior and firmware-specific wrapping still require owner validation.
Clipped acceptance deliberately requires a learned Cisco prompt, `$ ` marker and
the complete EVC `instance id <id> interface <port> detail` target. Other clipped forms
fail closed. Wrapped commands concatenate exactly without trimming body lines.
The existing configuration reader's one-second quiescence guard remains: an
unterminated embedded exact prompt paused for longer than that is inherently
ambiguous and remains a documented limitation.
