# =============================================================
#  TrustNova AI -- One-Shot Deploy Script
#
#  Usage:
#    .\deploy.ps1                           # auto-generates commit message
#    .\deploy.ps1 "feat: add new feature"   # custom commit message
#    .\deploy.ps1 -SkipGit                  # rebuild Docker only, no git push
#    .\deploy.ps1 -SkipDocker               # git push only, no Docker rebuild
#
#  What it does (in order):
#    1. git add -> commit -> push to GitHub  (triggers GitHub Actions CI)
#    2. docker compose build  (rebuilds backend, frontend, ml-service)
#    3. docker compose up -d  (rolling restart with new images)
# =============================================================

param(
    [string]$Message    = "",
    [switch]$SkipGit    = $false,
    [switch]$SkipDocker = $false
)

$ErrorActionPreference = "Continue"
$StartTime = Get-Date

function Write-Step { param($n, $text) Write-Host "`n[$n] $text" -ForegroundColor Cyan }
function Write-OK   { param($text)     Write-Host "  OK   $text" -ForegroundColor Green }
function Write-Warn { param($text)     Write-Host "  WARN $text" -ForegroundColor Yellow }
function Write-Fail { param($text)     Write-Host "  FAIL $text" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "  TrustNova AI -- One-Shot Deploy" -ForegroundColor Cyan
Write-Host "  ================================" -ForegroundColor Cyan
Write-Host ""

# ── 0. Pre-flight ──────────────────────────────────────────────────────────────

$ProjectRoot = $PSScriptRoot
Set-Location $ProjectRoot

Write-Step "0" "Pre-flight checks"

if (-not (Get-Command git    -ErrorAction SilentlyContinue)) { Write-Fail "git not found in PATH" }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Write-Fail "docker not found in PATH" }

$dockerVersion = docker info --format "{{.ServerVersion}}" 2>$null
if (-not $dockerVersion) { Write-Fail "Docker daemon is not running. Start Docker Desktop first." }

Write-OK "git + docker ready  (Docker Engine $dockerVersion)"
Write-OK "Project root: $ProjectRoot"


# ── 1. Git: stage -> commit -> push ───────────────────────────────────────────

if (-not $SkipGit) {
    Write-Step "1" "Git -- stage, commit, push to GitHub"

    $gitStatus = git status --porcelain 2>&1
    if (-not $gitStatus) {
        Write-Warn "No changes detected -- nothing to commit. Skipping git step."
    } else {
        Write-Host "  Changed files:"
        $gitStatus | ForEach-Object { Write-Host "    $_" }

        # Auto-generate commit message when not supplied
        if (-not $Message) {
            $changedFiles = (git diff --name-only HEAD 2>$null) -split "`n" | Where-Object { $_ }
            $newFiles     = (git ls-files --others --exclude-standard 2>$null) -split "`n" | Where-Object { $_ }
            $allChanged   = @($changedFiles) + @($newFiles) | Where-Object { $_ }

            $prefix = "chore"
            foreach ($f in $allChanged) {
                if ($f -match "^src/api/routes/|^src/")    { $prefix = "feat";    break }
                if ($f -match "^frontend-react/")           { $prefix = "feat(ui)"; break }
                if ($f -match "^deployment/|^\.github/")    { $prefix = "ci";      break }
                if ($f -match "^tests/")                    { $prefix = "test";    break }
            }

            $fileCount = $allChanged.Count
            $shortList = ($allChanged | Select-Object -First 3) -join ", "
            $suffix    = if ($fileCount -gt 3) { " (+$($fileCount - 3) more)" } else { "" }
            $Message   = "${prefix}: update ${shortList}${suffix}"
        }

        Write-Host "  Commit message: $Message"

        # Suppress LF/CRLF warnings — they are informational, not errors
        git add -A 2>&1 | Where-Object { $_ -notmatch "^warning:" } | ForEach-Object { Write-Host "  git: $_" }
        if ($LASTEXITCODE -ne 0) { Write-Fail "git add failed (exit $LASTEXITCODE)" }

        # Write commit message to a temp file to avoid shell quoting issues
        $tmpMsg = [System.IO.Path]::GetTempFileName()
        Set-Content -Path $tmpMsg -Value "$Message`n`nCo-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>" -Encoding utf8
        git commit -F $tmpMsg 2>&1 | Where-Object { $_ -notmatch "^warning:" } | ForEach-Object { Write-Host "  git: $_" }
        Remove-Item $tmpMsg -Force
        if ($LASTEXITCODE -ne 0) { Write-Fail "git commit failed (exit $LASTEXITCODE)" }

        Write-OK "Committed: $Message"

        git push origin main 2>&1 | Where-Object { $_ -notmatch "^warning:" } | ForEach-Object { Write-Host "  git: $_" }
        if ($LASTEXITCODE -ne 0) { Write-Fail "git push failed -- check credentials or branch protection rules" }

        Write-OK "Pushed to origin/main -- GitHub Actions CI triggered automatically"
        Write-OK "Watch CI at: https://github.com/prakash-94/Trustnova-AI/actions"
    }
} else {
    Write-Warn "Skipping git (-SkipGit flag set)"
}


# ── 2. Docker: build the 3 custom images ──────────────────────────────────────

if (-not $SkipDocker) {
    Write-Step "2" "Docker -- build images (backend, frontend, ml-service)"

    $composeFile = Join-Path $ProjectRoot "deployment\docker-compose.yml"

    # Build only the 3 images we own; chromadb / prometheus / grafana are pulled
    docker compose -f $composeFile build --parallel backend frontend ml-service
    if ($LASTEXITCODE -ne 0) { Write-Fail "docker compose build failed" }

    Write-OK "Images built:"
    docker images --filter "reference=trusnova*" --format "    {{.Repository}}:{{.Tag}}  ({{.Size}})" | Write-Host


    # ── 3. Docker: rolling restart ─────────────────────────────────────────────

    Write-Step "3" "Docker -- rolling restart (docker compose up -d)"

    docker compose -f $composeFile up -d --no-deps backend frontend ml-service
    if ($LASTEXITCODE -ne 0) { Write-Fail "docker compose up failed" }

    Write-Host "  Waiting 10s for containers to initialise..."
    Start-Sleep -Seconds 10

    Write-OK "Container status:"
    docker compose -f $composeFile ps 2>&1 | ForEach-Object { Write-Host "    $_" }


    # ── 4. Smoke tests ─────────────────────────────────────────────────────────

    Write-Step "4" "Smoke tests"

    $endpoints = @(
        @{ label = "Backend  /health"; url = "http://localhost:8001/health" },
        @{ label = "Frontend /      "; url = "http://localhost:80"           },
        @{ label = "ML Svc   /health"; url = "http://localhost:8003/health"  },
        @{ label = "ChromaDB heartbt"; url = "http://localhost:8002/api/v2/heartbeat" },
        @{ label = "Prometheus      "; url = "http://localhost:9090/-/healthy" },
        @{ label = "Grafana         "; url = "http://localhost:3000/api/health" }
    )

    $allOk = $true
    foreach ($ep in $endpoints) {
        try {
            $r = Invoke-WebRequest -Uri $ep.url -UseBasicParsing -TimeoutSec 8 -ErrorAction Stop
            Write-OK "$($ep.label)  HTTP $($r.StatusCode)"
        } catch {
            Write-Warn "$($ep.label)  $($_.Exception.Message)"
            $allOk = $false
        }
    }

    if (-not $allOk) {
        Write-Warn "Some endpoints not ready yet -- containers may still be initialising."
        Write-Host "  Check with:  docker compose -f deployment/docker-compose.yml ps"
    }
} else {
    Write-Warn "Skipping Docker build/restart (-SkipDocker flag set)"
}


# ── Summary ────────────────────────────────────────────────────────────────────

$elapsed = [math]::Round(((Get-Date) - $StartTime).TotalSeconds)

Write-Host ""
Write-Host "  Deploy complete in ${elapsed}s" -ForegroundColor Green
Write-Host ""
Write-Host "  Services:"
Write-Host "    App        ->  http://localhost:80"
Write-Host "    API docs   ->  http://localhost:8001/docs"
Write-Host "    ML Service ->  http://localhost:8003"
Write-Host "    Grafana    ->  http://localhost:3000   (admin / changeme)"
Write-Host "    Prometheus ->  http://localhost:9090"
Write-Host ""
Write-Host "  GitHub:"
Write-Host "    Repo       ->  https://github.com/prakash-94/Trustnova-AI"
Write-Host "    Actions    ->  https://github.com/prakash-94/Trustnova-AI/actions"
Write-Host ""
