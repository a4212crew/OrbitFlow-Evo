param(
    [string]$Repo = "a4212crew/OrbitFlow-Evo"
)

$ErrorActionPreference = "Stop"

Write-Host "Validating OrbitFlow-Evo local Codex prerequisites..."

& gh auth status
if ($LASTEXITCODE -ne 0) { throw "GitHub CLI authentication failed." }

& codex --version
if ($LASTEXITCODE -ne 0) { throw "Codex CLI is not available." }

$actualRepo = (& gh repo view $Repo --json nameWithOwner --jq ".nameWithOwner").Trim()
if ($LASTEXITCODE -ne 0) { throw "Unable to read repository identity." }
if ($actualRepo -ne $Repo) {
    throw "Repository identity mismatch. Expected '$Repo' but GitHub returned '$actualRepo'."
}

$labels = @(
    @{ Name = "codex-task"; Color = "1D76DB"; Description = "Task approved for Codex implementation" },
    @{ Name = "codex-running"; Color = "FBCA04"; Description = "Codex implementation is running locally" },
    @{ Name = "codex-review"; Color = "5319E7"; Description = "Waiting for Atlas review" },
    @{ Name = "codex-revise"; Color = "D93F0B"; Description = "Atlas requested another Codex revision" },
    @{ Name = "codex-approved"; Color = "0E8A16"; Description = "Atlas review passed" },
    @{ Name = "codex-pr"; Color = "8250DF"; Description = "Task has an open Codex pull request" },
    @{ Name = "codex-failed"; Color = "B60205"; Description = "Codex controller failed" },
    @{ Name = "codex-replan-required"; Color = "B60205"; Description = "15-iteration limit reached; implementation plan must be revisited" }
)

foreach ($label in $labels) {
    & gh label create $label.Name --repo $Repo --color $label.Color --description $label.Description --force | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create or update label '$($label.Name)'."
    }
}

Write-Host ""
Write-Host "Bootstrap complete."
Write-Host "Repository: $Repo"
Write-Host "GitHub CLI: authenticated"
Write-Host "Codex CLI: installed"
Write-Host ""
Write-Host "Codex authentication must use your ChatGPT account."
Write-Host "If needed, run: codex login"
Write-Host ""
Write-Host "No OPENAI_API_KEY is required by this orchestration."
