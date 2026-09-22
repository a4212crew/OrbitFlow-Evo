param(
    [string]$Repo = "a4212crew/OrbitFlow-Evo",
    [switch]$Watch,
    [int]$PollSeconds = 20,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

if ($PollSeconds -lt 5) {
    throw "PollSeconds must be at least 5."
}

function Invoke-Gh {
    param([string[]]$Args)
    $output = & gh @Args 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "gh $($Args -join ' ') failed: $($output | Out-String)"
    }
    return ($output | Out-String)
}

function Invoke-Git {
    param([string[]]$Args, [string]$WorkingDirectory)
    Push-Location $WorkingDirectory
    try {
        $output = & git @Args 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "git $($Args -join ' ') failed: $($output | Out-String)"
        }
        return ($output | Out-String)
    }
    finally {
        Pop-Location
    }
}

function Set-IssueLabels {
    param([int]$IssueNumber, [string[]]$Add = @(), [string[]]$Remove = @())
    $args = @("issue", "edit", "$IssueNumber", "--repo", $Repo)
    foreach ($label in $Remove) { $args += @("--remove-label", $label) }
    foreach ($label in $Add) { $args += @("--add-label", $label) }
    Invoke-Gh $args | Out-Null
}

function Add-IssueComment {
    param([int]$IssueNumber, [string]$Body)
    $temp = Join-Path $env:TEMP "orbitflow-codex-comment-$IssueNumber.md"
    Set-Content -Path $temp -Value $Body -Encoding UTF8
    try {
        Invoke-Gh @("issue", "comment", "$IssueNumber", "--repo", $Repo, "--body-file", $temp) | Out-Null
    }
    finally {
        Remove-Item $temp -Force -ErrorAction SilentlyContinue
    }
}

function Get-IterationState {
    param([int]$IssueNumber)
    $json = Invoke-Gh @("issue", "view", "$IssueNumber", "--repo", $Repo, "--json", "comments")
    $data = $json | ConvertFrom-Json
    $maxIteration = 0
    $latestAtlasReview = $null
    $owner = $Repo.Split('/')[0]

    foreach ($comment in $data.comments) {
        if ($comment.body -match '<!-- orbitflow-codex-iteration:(\d+) -->') {
            $value = [int]$Matches[1]
            if ($value -gt $maxIteration) { $maxIteration = $value }
        }

        if ($comment.author.login -eq $owner -and $comment.body -like '*<!-- atlas-review -->*') {
            $latestAtlasReview = $comment.body
        }
    }

    return @{ Iteration = $maxIteration; AtlasReview = $latestAtlasReview }
}

function Get-NextTask {
    foreach ($label in @("codex-revise", "codex-task")) {
        $json = Invoke-Gh @("issue", "list", "--repo", $Repo, "--label", $label, "--state", "open", "--limit", "1", "--json", "number,title,body,url")
        $issues = $json | ConvertFrom-Json
        if ($issues -and $issues.Count -gt 0) {
            $mode = if ($label -eq "codex-revise") { "revision" } else { "initial" }
            return @{ Mode = $mode; Issue = $issues[0] }
        }
    }
    return $null
}

function Ensure-Worktree {
    param([int]$IssueNumber, [string]$Mode, [string]$RepoRoot, [string]$WorktreeRoot)

    $branch = "codex/issue-$IssueNumber"
    $path = Join-Path $WorktreeRoot "issue-$IssueNumber"
    Invoke-Git @("fetch", "origin", "--prune") $RepoRoot | Out-Null

    if ($Mode -eq "initial") {
        $remote = & git -C $RepoRoot ls-remote --heads origin $branch 2>$null
        if ($LASTEXITCODE -ne 0) { throw "Unable to check remote branch '$branch'." }
        if ($remote) { throw "Task branch '$branch' already exists. Refusing duplicate initial execution." }
        if (Test-Path $path) { throw "Worktree path '$path' already exists. Clean it up before retrying." }
        Invoke-Git @("worktree", "add", "-b", $branch, $path, "origin/main") $RepoRoot | Out-Null
    }
    else {
        $remote = & git -C $RepoRoot ls-remote --heads origin $branch 2>$null
        if (-not $remote) { throw "Revision requested but remote task branch '$branch' does not exist." }

        Invoke-Git @("fetch", "origin", $branch) $RepoRoot | Out-Null

        if (-not (Test-Path $path)) {
            $localBranch = & git -C $RepoRoot branch --list $branch
            if ($localBranch) {
                Invoke-Git @("worktree", "add", $path, $branch) $RepoRoot | Out-Null
            }
            else {
                Invoke-Git @("worktree", "add", "-b", $branch, $path, "origin/$branch") $RepoRoot | Out-Null
            }
        }

        Invoke-Git @("reset", "--hard", "origin/$branch") $path | Out-Null
        Invoke-Git @("clean", "-fd") $path | Out-Null
    }

    return @{ Branch = $branch; Path = $path }
}

function Invoke-CodexTask {
    param([hashtable]$Task)

    $issue = $Task.Issue
    $mode = $Task.Mode
    $issueNumber = [int]$issue.number

    $repoRoot = (& git rev-parse --show-toplevel).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Run the controller from inside the OrbitFlow-Evo repository." }

    $actualRepo = (Invoke-Gh @("repo", "view", $Repo, "--json", "nameWithOwner", "--jq", ".nameWithOwner")).Trim()
    if ($actualRepo -ne $Repo) { throw "Repository identity mismatch. Expected '$Repo', got '$actualRepo'." }

    $status = (& git -C $repoRoot status --porcelain) | Out-String
    if (-not [string]::IsNullOrWhiteSpace($status)) {
        throw "Main checkout is dirty. Commit, stash, or discard local changes before running Codex."
    }

    $worktreeRoot = Join-Path (Split-Path $repoRoot -Parent) "OrbitFlow-Evo-worktrees"
    New-Item -ItemType Directory -Path $worktreeRoot -Force | Out-Null

    $state = Get-IterationState $issueNumber

    if ($mode -eq "revision") {
        if ($state.Iteration -ge 15) {
            Set-IssueLabels $issueNumber @("codex-replan-required") @("codex-revise", "codex-running", "codex-review")
            Add-IssueComment $issueNumber "The current implementation plan has reached the 15-iteration limit. Automated Codex revision is stopped. Atlas and the user must revisit and approve the implementation plan before a new cycle begins."
            Write-Host "Issue #$issueNumber reached the 15-iteration limit."
            return
        }

        if ([string]::IsNullOrWhiteSpace($state.AtlasReview)) {
            throw "Revision requested but no owner-authored atlas-review marker comment was found."
        }

        $iteration = $state.Iteration + 1
    }
    else {
        if ($state.Iteration -gt 0) {
            throw "Issue #$issueNumber already has Codex iteration history; refusing a second initial run."
        }
        $iteration = 1
    }

    $worktree = Ensure-Worktree $issueNumber $mode $repoRoot $worktreeRoot
    $preamblePath = Join-Path $worktree.Path "scripts\orchestration\task-preamble.md"
    $preamble = Get-Content $preamblePath -Raw

    $parts = @(
        $preamble,
        "",
        "# GitHub Task",
        "Issue #$issueNumber: $($issue.title)",
        "",
        $issue.body,
        "",
        "# Iteration",
        "This is implementation/review iteration $iteration of a maximum 15 under the current approved plan."
    )

    if ($mode -eq "revision") {
        $parts += @(
            "",
            "# Atlas Review Corrections",
            $state.AtlasReview,
            "",
            "Address the Atlas review findings only and preserve unrelated working behavior."
        )
    }

    $prompt = $parts -join [Environment]::NewLine

    if ($DryRun) {
        Write-Host ""
        Write-Host "DRY RUN: issue #$issueNumber, mode=$mode, iteration=$iteration"
        Write-Host "Branch: $($worktree.Branch)"
        Write-Host "Worktree: $($worktree.Path)"
        Write-Host "--------------------------------"
        Write-Host $prompt
        Write-Host "--------------------------------"
        return
    }

    Set-IssueLabels $issueNumber @("codex-running") @("codex-task", "codex-revise", "codex-review", "codex-failed")

    $outputFile = Join-Path $env:TEMP "orbitflow-codex-output-$issueNumber.txt"
    Remove-Item $outputFile -Force -ErrorAction SilentlyContinue

    Write-Host "Starting local Codex CLI for issue #$issueNumber (iteration $iteration/15)..."

    Push-Location $worktree.Path
    try {
        $previousPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & codex exec $prompt 2>&1 | Tee-Object -FilePath $outputFile
        $codexExit = $LASTEXITCODE
        $ErrorActionPreference = $previousPreference
    }
    finally {
        Pop-Location
    }

    if ($codexExit -ne 0) { throw "Codex exited with code $codexExit." }

    $changes = (& git -C $worktree.Path status --porcelain) | Out-String
    if ([string]::IsNullOrWhiteSpace($changes)) { throw "Codex completed without repository changes." }

    $previousPythonPath = $env:PYTHONPATH
    $env:PYTHONPATH = "src"
    Push-Location $worktree.Path
    try {
        & python -m pytest -q
        $testExit = $LASTEXITCODE
    }
    finally {
        Pop-Location
        $env:PYTHONPATH = $previousPythonPath
    }

    $testStatus = if ($testExit -eq 0) { "passed" } else { "failed (exit $testExit)" }

    Invoke-Git @("add", "-A") $worktree.Path | Out-Null
    Invoke-Git @("commit", "-m", "Codex: issue #$issueNumber iteration $iteration") $worktree.Path | Out-Null
    Invoke-Git @("push", "--set-upstream", "origin", $worktree.Branch) $worktree.Path | Out-Null

    if ($mode -eq "initial") {
        $prBody = "Implements OrbitFlow-Evo issue #$issueNumber." + [Environment]::NewLine + [Environment]::NewLine +
                  "Generated by the local ChatGPT-authenticated Codex CLI orchestration." + [Environment]::NewLine + [Environment]::NewLine +
                  "Iteration: $iteration/15" + [Environment]::NewLine +
                  "Automated tests: $testStatus" + [Environment]::NewLine + [Environment]::NewLine +
                  "Atlas review and explicit human merge approval are required."

        $prFile = Join-Path $env:TEMP "orbitflow-codex-pr-$issueNumber.md"
        Set-Content -Path $prFile -Value $prBody -Encoding UTF8
        try {
            $prUrl = (Invoke-Gh @("pr", "create", "--repo", $Repo, "--head", $worktree.Branch, "--base", "main", "--title", "Codex: #$issueNumber $($issue.title)", "--body-file", $prFile)).Trim()
        }
        finally {
            Remove-Item $prFile -Force -ErrorAction SilentlyContinue
        }
    }
    else {
        $prUrl = (Invoke-Gh @("pr", "view", $worktree.Branch, "--repo", $Repo, "--json", "url", "--jq", ".url")).Trim()
    }

    $codexOutput = if (Test-Path $outputFile) { Get-Content $outputFile -Raw } else { "" }
    if ($codexOutput.Length -gt 6000) {
        $codexOutput = "[output truncated to last 6000 characters]" + [Environment]::NewLine + $codexOutput.Substring($codexOutput.Length - 6000)
    }

    $comment = "<!-- orbitflow-codex-iteration:$iteration -->" + [Environment]::NewLine +
               "Codex iteration $iteration/15 is ready for Atlas review." + [Environment]::NewLine + [Environment]::NewLine +
               "PR: $prUrl" + [Environment]::NewLine +
               "Automated tests: $testStatus" + [Environment]::NewLine + [Environment]::NewLine +
               "Codex output:" + [Environment]::NewLine + $codexOutput.TrimEnd()

    Add-IssueComment $issueNumber $comment
    Set-IssueLabels $issueNumber @("codex-review", "codex-pr") @("codex-running", "codex-failed")
    Remove-Item $outputFile -Force -ErrorAction SilentlyContinue

    Write-Host "Issue #$issueNumber moved to codex-review."
    Write-Host "PR: $prUrl"
}

function Process-One {
    $task = Get-NextTask
    if (-not $task) {
        Write-Host "No codex-task or codex-revise issue is waiting."
        return $false
    }

    try {
        Invoke-CodexTask $task
    }
    catch {
        $issueNumber = [int]$task.Issue.number
        Write-Error $_
        try {
            Set-IssueLabels $issueNumber @("codex-failed") @("codex-running")
            Add-IssueComment $issueNumber "Local Codex orchestration failed: $($_.Exception.Message)"
        }
        catch {
            Write-Warning "Failed to update GitHub failure state: $($_.Exception.Message)"
        }
    }

    return $true
}

do {
    $processed = Process-One
    if (-not $Watch) { break }
    if (-not $processed) { Start-Sleep -Seconds $PollSeconds }
} while ($true)
