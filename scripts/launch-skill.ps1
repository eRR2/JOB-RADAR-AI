# Invoked by the skill. No system installation, profile edits, registry or OS tasks.
[CmdletBinding()]
param(
    [switch]$ApproveBootstrap,
    [switch]$Check,
    [switch]$ManagedOnly,
    [switch]$NoBrowser,
    [ValidateRange(1,65535)][int]$Port = 8767,
    [string]$Database = '.private/state.sqlite3'
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$private = Join-Path $root '.private'
$databasePath = [IO.Path]::GetFullPath((Join-Path $root $Database))
if (-not $databasePath.StartsWith($private + '\', [StringComparison]::OrdinalIgnoreCase) -or [IO.Path]::GetExtension($databasePath) -ne '.sqlite3') {
    throw 'Database must be a .sqlite3 file below this checkout .private directory.'
}
if ($root.Contains('"') -or $Database.Contains('"')) { throw 'Unsupported quote in launch path.' }
$runtime = Join-Path $private 'runtime'
$python = Join-Path $runtime 'venv/Scripts/python.exe'
$bun = Join-Path $runtime 'bun/bun-windows-x64/bun.exe'
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'runtime-manifest.json') -Raw | ConvertFrom-Json
$codexDirectory = Join-Path $runtime ('codex/' + $manifest.codex.version)
if (Test-Path -LiteralPath (Join-Path $codexDirectory 'codex.exe')) { $env:PATH = $codexDirectory + ';' + $env:PATH }
if (-not $ManagedOnly) {
    if (-not (Test-Path -LiteralPath $python)) { $python = Join-Path $root '.venv/Scripts/python.exe' }
    if (-not (Test-Path -LiteralPath $bun)) {
        $existing = Get-Command bun.exe -ErrorAction SilentlyContinue
        $bun = if ($existing) { $existing.Source } else { Join-Path $env:USERPROFILE '.bun/bin/bun.exe' }
    }
}
$pythonReady = $false
if (Test-Path -LiteralPath $python) {
    try {
        & $python -c 'import sys,jsonschema,pypdf; sys.exit(0 if sys.version_info >= (3,11) else 1)' 2>$null
        $pythonReady = $LASTEXITCODE -eq 0
    } catch { $pythonReady = $false }
}
$bunReady = $false
if (Test-Path -LiteralPath $bun) {
    try {
        & $bun --version *> $null
        $bunReady = $LASTEXITCODE -eq 0
    } catch { $bunReady = $false }
}
if ($Check) {
    [pscustomobject]@{ python_ready=$pythonReady; bun_ready=$bunReady; bootstrap_required=(-not ($pythonReady -and $bunReady)); platform='Windows x64'; storage='.private'; system_install=$false } | ConvertTo-Json -Compress
    exit 0
}
if (-not ($pythonReady -and $bunReady) -and -not $ApproveBootstrap) {
    Write-Output 'BOOTSTRAP_APPROVAL_REQUIRED: Download pinned uv, managed Python, locked Python wheels and/or Bun into this checkout .private/runtime. No system-wide installation. Ask the user, then invoke again with -ApproveBootstrap.'
    exit 2
}

# Serialize launches and bootstrap so two skill invocations cannot race.
$sha = [Security.Cryptography.SHA256]::Create()
$workspaceId = ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($root + "`n" + $databasePath)))).Replace('-','').ToLowerInvariant()
$mutex = New-Object Threading.Mutex($false, ('Local\JOB-RADAR-AI-' + $workspaceId))
$acquired = $false
function Get-Health {
    try { Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 2 } catch { $null }
}
function Assert-Health($health) {
    if ($health.app -ne 'JOB-RADAR-AI' -or $health.workspace_id -ne $workspaceId -or -not $health.skill_mode) {
        throw 'This port belongs to another workspace or V1. Close it or choose another port; nothing was stopped.'
    }
}
function Get-Archive($name) {
    $entry = $manifest.$name
    $archive = Join-Path $runtime "$name.zip"
    if (-not (Test-Path -LiteralPath $archive)) { Invoke-WebRequest -UseBasicParsing -Uri $entry.url -OutFile $archive }
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.sha256) {
        throw 'Runtime checksum mismatch. Nothing from this archive was executed.'
    }
    Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $runtime $name) -Force
    Join-Path (Join-Path $runtime $name) $entry.executable
}
try {
    try { $acquired = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $acquired=$true }
    if (-not $acquired) { throw 'Another skill launch is active. Wait for it to finish.' }
    $health = Get-Health
    if ($health) {
        Assert-Health $health
    } else {
        # Fail before installation or spawning when a non-JOB-RADAR service owns the port.
        $probe = New-Object Net.Sockets.TcpClient
        try { $probe.Connect('127.0.0.1',$Port); throw 'Local port already occupied. Choose another port.' }
        catch [Net.Sockets.SocketException] { } finally { $probe.Dispose() }
        if (-not ($pythonReady -and $bunReady)) {
            if ([Environment]::Is64BitOperatingSystem -ne $true -or $env:PROCESSOR_ARCHITECTURE -ne 'AMD64') {
                throw 'Automatic bootstrap is currently verified only for Windows x64.'
            }
            New-Item -ItemType Directory -Path $runtime -Force | Out-Null
            # All runtime download/cache/temp files stay inside the private workspace.
            $env:TEMP = Join-Path $runtime 'tmp'; $env:TMP = $env:TEMP
            New-Item -ItemType Directory -Path $env:TEMP -Force | Out-Null
            $env:UV_PYTHON_INSTALL_DIR = Join-Path $runtime 'python'
            $env:UV_PYTHON_INSTALL_BIN = 'false'
            $env:UV_PYTHON_NO_REGISTRY = 'true'
            $env:UV_CACHE_DIR = Join-Path $runtime 'cache'
            if (-not $pythonReady) {
                $uv = Join-Path $runtime 'uv/uv.exe'
                if (-not (Test-Path -LiteralPath $uv)) { $uv = Get-Archive 'uv' }
                & $uv --no-config python install $manifest.python --no-bin --no-registry
                if ($LASTEXITCODE) { throw 'Private Python download failed; no fallback installation attempted.' }
                & $uv --no-config venv --python $manifest.python --managed-python (Join-Path $runtime 'venv')
                if ($LASTEXITCODE) { throw 'Private Python environment creation failed.' }
                $python = Join-Path $runtime 'venv/Scripts/python.exe'
                & $uv --no-config pip install --python $python --only-binary :all: -r (Join-Path $root 'requirements.lock.txt')
                if ($LASTEXITCODE) { throw 'Locked Python dependency installation failed.' }
            }
            if (-not $bunReady) { $bun = Get-Archive 'bun' }
        }
        $env:PATH = (Split-Path -Parent $bun) + ';' + $env:PATH
        $diagnostics = Join-Path (Join-Path $private 'launch') $workspaceId
        New-Item -ItemType Directory -Path $diagnostics -Force | Out-Null
        # Windows PowerShell Start-Process can leak the calling agent's pipe handles
        # into the long-lived server. Close all unrelated handles explicitly so the
        # launch command completes independently of the dashboard's lifetime.
        $spawn = @'
import pathlib,subprocess,sys
root,port,db,logs=sys.argv[1:]
logs=pathlib.Path(logs)
with (logs/'stdout.log').open('ab') as out, (logs/'stderr.log').open('ab') as err:
    p=subprocess.Popen([sys.executable,'-m','job_radar_ai','--root',root,'--port',port,'--database',db,'--skill-mode','--no-browser'],cwd=root,stdin=subprocess.DEVNULL,stdout=out,stderr=err,close_fds=True,creationflags=subprocess.CREATE_NO_WINDOW)
print(p.pid)
'@
        $serverId = & $python -c $spawn $root "$Port" $Database $diagnostics
        if ($LASTEXITCODE -ne 0) { throw 'Dashboard process could not be started.' }
        for ($attempt=0; $attempt -lt 30; $attempt++) {
            $health = Get-Health
            if ($health) { Assert-Health $health; break }
            if (-not (Get-Process -Id $serverId -ErrorAction SilentlyContinue)) { throw 'Dashboard process exited. Inspect private launch diagnostics.' }
            Start-Sleep -Milliseconds 300
        }
        if (-not $health) { throw 'Dashboard readiness timed out. No browser success claimed.' }
    }
    $url = "http://127.0.0.1:$Port"
    if (-not $NoBrowser) { Start-Process $url }
    [pscustomobject]@{url=$url; workspace_id=$workspaceId; skill_mode=$true; ready=$true; browser_requested=(-not $NoBrowser)} | ConvertTo-Json -Compress
} finally {
    if ($acquired) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
    $sha.Dispose()
}
