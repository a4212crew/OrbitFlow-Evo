# Offline configuration plan — operator manual

**Entry point:** `scripts/configuration_plan.py` (delegates to `orbitflow.configuration.cli`). Produces and reviews **offline plans only**. There is no apply command and no device connection.

## Prerequisites
Python virtual environment and dependencies per [repository setup](../../README.md). Supply a valid normalized JSON request and local inventory JSON for plan creation. Never include credentials in requests.

## Commands and parameters
- `create REQUEST`: required request JSON path; optional `--inventory PATH` (default `data/inventory/inventory.json`) and `--output PATH` (default `outputs/runs/configuration/<change-id>/plan.json`).
- `validate PLAN` and `preview PLAN`: required plan path; no additional CLI options.
- `approve PLAN`: required `--actor STRING`, `--digest STRING` (exact preview digest), `--expires-at ISO8601_WITH_TIMEZONE`; optional `--authority PATH` (default `data/configuration`).
- `reject PLAN`, `expire PLAN`: required `--actor STRING`; optional `--authority PATH` (default `data/configuration`).
- `verify-approval PLAN`: optional `--authority PATH` (same default).

## Examples
Linux:
```bash
python scripts/configuration_plan.py create reviewed-request.json --inventory data/inventory/inventory.json
python scripts/configuration_plan.py preview outputs/runs/configuration/CHANGE_ID/plan.json
python scripts/configuration_plan.py validate outputs/runs/configuration/CHANGE_ID/plan.json
```
PowerShell:
```powershell
python scripts/configuration_plan.py create .\reviewed-request.json --inventory .\data\inventory\inventory.json
python scripts/configuration_plan.py preview .\outputs\runs\configuration\CHANGE_ID\plan.json
```
The request must conform to the normalized plan contract. `CHANGE_ID` is a **placeholder**, not literal generated data. For worked inputs see [offline v1 contract](../architecture/configuration/offline-plans.md).

## Expected outcomes
`create` prints `Created plan <digest>`; `validate` prints `Valid offline plan <digest>`; `preview` renders the review. `approve`, `reject`, `expire` and `verify-approval` create/check local approval records and print the resulting state. Invalid inputs or unavailable storage are refused with exit code 2. **Approval does not execute configuration on devices.**
