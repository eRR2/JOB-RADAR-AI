# Agent-operated optional private CLI setup. Never evaluate a downloaded script.
[CmdletBinding()]
param([switch]$ApproveDownload, [switch]$Login, [switch]$PrivateOnly)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$entry = (Get-Content -LiteralPath (Join-Path $PSScriptRoot 'runtime-manifest.json') -Raw | ConvertFrom-Json).codex
$folder = Join-Path $root ('.private/runtime/codex/' + $entry.version)
$binary = Join-Path $folder 'codex.exe'
if (-not (Test-Path -LiteralPath $binary) -and -not $PrivateOnly) {
    $existing = Get-Command codex.exe -ErrorAction SilentlyContinue
    if ($existing) { $binary = $existing.Source }
    else {
        $npm = Join-Path $env:APPDATA 'npm/node_modules/@openai/codex'
        if (Test-Path -LiteralPath $npm) {
            $native = Get-ChildItem -LiteralPath $npm -Recurse -Filter 'codex.exe' -File | Select-Object -First 1
            if ($native) { $binary = $native.FullName }
        }
    }
}
if (-not (Test-Path -LiteralPath $binary)) {
    if (-not $ApproveDownload) {
        Write-Output ('CODEX_DOWNLOAD_APPROVAL_REQUIRED: Codex CLI ' + $entry.version + ' Windows x64; official openai/codex ZIP; SHA-256 ' + $entry.sha256 + '; destination .private/runtime/codex. No system installation. Ask approval before -ApproveDownload.')
        exit 2
    }
    if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -ne 'AMD64') { throw 'Private Codex bootstrap supports Windows x64 only.' }
    # Serialize download/extraction; a partial binary must never become discoverable.
    New-Item -ItemType Directory -Path $folder -Force | Out-Null
    $lock = [IO.File]::Open((Join-Path $folder 'setup.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    try {
        $archive = Join-Path $folder 'codex.zip'
        if (-not (Test-Path -LiteralPath $archive)) { Invoke-WebRequest -UseBasicParsing -Uri $entry.url -OutFile $archive }
        if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.sha256) { throw 'Codex checksum mismatch. No downloaded code was executed; remove the damaged private ZIP before retrying.' }
        # Keep the official package's adjacent resources/helpers with its native executable.
        $unpacked = $folder
        Expand-Archive -LiteralPath $archive -DestinationPath $unpacked -Force
        Copy-Item -LiteralPath (Join-Path $unpacked $entry.executable) -Destination ($binary + '.pending')
        Move-Item -LiteralPath ($binary + '.pending') -Destination $binary
    } finally { $lock.Dispose() }
}
if ($Login) {
    # Official login owns credentials and opens its browser flow. Never read/copy auth files.
    Start-Process -FilePath $binary -ArgumentList 'login' -WindowStyle Hidden | Out-Null
}
$info = New-Object Diagnostics.ProcessStartInfo
$info.FileName=$binary; $info.Arguments='login status'; $info.UseShellExecute=$false; $info.CreateNoWindow=$true
$info.RedirectStandardOutput=$true; $info.RedirectStandardError=$true
$process=New-Object Diagnostics.Process
$process.StartInfo=$info
try {
    $process.Start() | Out-Null
    $output=$process.StandardOutput.ReadToEndAsync(); $errors=$process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit(15000)) { $process.Kill(); throw 'Codex login status timed out; no inference or retry attempted.' }
    $statusText=($output.Result + $errors.Result).ToLowerInvariant()
    $authenticated=$process.ExitCode -eq 0 -and $statusText.Contains('logged in') -and -not $statusText.Contains('api key')
} finally { $process.Dispose() }
[pscustomobject]@{installed=$true; login_command_started=[bool]$Login; login_status_ok=$authenticated; inference_verified=$false; system_install=$false} | ConvertTo-Json -Compress
