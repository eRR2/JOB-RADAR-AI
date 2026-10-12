# Run locally AFTER Codex has downloaded, extracted and reviewed the public repository archive.
# No network, runtime installation, credential access, database migration or OS tasks.
[CmdletBinding()]
param(
    [string]$Destination = (Join-Path $env:LOCALAPPDATA 'JOB-RADAR-AI/app'),
    [string]$Revision = 'local-reviewed'
)
$ErrorActionPreference='Stop'
function File-Sha256([string]$path) {
    $stream=[IO.File]::OpenRead($path); $algorithm=[Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-','') }
    finally { $algorithm.Dispose(); $stream.Dispose() }
}
$source=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$target=[IO.Path]::GetFullPath($Destination)
if ($source -eq $target -or $target.StartsWith($source+'\',[StringComparison]::OrdinalIgnoreCase) -or $source.StartsWith($target+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Source package and application workspace must be separate.' }
foreach ($name in @('.private','.tools','.git','.venv','node_modules','.env','profiles','reports','backups')) {
    if (Test-Path -LiteralPath (Join-Path $source $name)) { throw 'Use a clean public repository archive; never install from a personal checkout.' }
}
foreach ($name in @('README.md','scripts/launch-skill.ps1','skills/job-radar-ai/SKILL.md')) {
    if (-not (Test-Path -LiteralPath (Join-Path $source $name))) { throw 'Incomplete application package.' }
}
function Safe-Target([string]$relative) {
    if ($relative -match '(^|[\\/])(\.private|\.tools|\.git|\.venv|node_modules|profiles|reports|backups|\.env[^\\/]*|auth\.json|credentials(?:\.json)?|sessions?)([\\/]|$)' -or $relative -match '\.(sqlite[^.]*|db|pdf|docx|key|pem)$') { throw 'Private material is forbidden in the source package.' }
    $path=[IO.Path]::GetFullPath((Join-Path $target $relative))
    if (-not $path.StartsWith($target+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Package path escapes the application workspace.' }
    $ancestor=$path
    while ($ancestor -and $ancestor.Length -ge $target.Length) {
        if ((Test-Path -LiteralPath $ancestor) -and ((Get-Item -LiteralPath $ancestor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Linked destinations are unsupported; no files were written.' }
        $ancestor=Split-Path -Parent $ancestor
    }
    return $path
}
if (@(Get-ChildItem -LiteralPath $source -Recurse -Force -Directory | Where-Object {$_.Attributes -band [IO.FileAttributes]::ReparsePoint}).Count) { throw 'Source package links are unsupported.' }
$files=@(Get-ChildItem -LiteralPath $source -Recurse -Force -File)
$hashes=@{}
foreach ($file in $files) {
    if ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Source package links are unsupported.' }
    $relative=$file.FullName.Substring($source.Length+1)
    $null=Safe-Target $relative
    $hashes[$relative]=File-Sha256 $file.FullName
}
$manifestPath=Join-Path $target '.private/install-manifest.json'
if ((Test-Path -LiteralPath (Join-Path $target '.private')) -and ((Get-Item -LiteralPath (Join-Path $target '.private') -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Linked private storage is unsupported; use an independent local workspace.' }
$previous=$null
if (Test-Path -LiteralPath $target) {
    if (Test-Path -LiteralPath $manifestPath) {
        $previous=Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
        foreach ($property in $previous.files.PSObject.Properties) {
            $path=Safe-Target $property.Name
            if (-not (Test-Path -LiteralPath $path) -or (File-Sha256 $path) -ne $property.Value) { throw 'Local application files changed. Upgrade refused; existing data and code were not overwritten.' }
        }
        foreach ($relative in $hashes.Keys) {
            if (@($previous.files.PSObject.Properties.Name) -notcontains $relative -and (Test-Path -LiteralPath (Safe-Target $relative))) { throw 'A new source file conflicts with an existing local file. Upgrade refused before copying.' }
        }
    } elseif (@(Get-ChildItem -LiteralPath $target -Force).Count) { throw 'Existing directory is not managed by this installer. Preserve it; do not reset or overwrite.' }
}
# Probe every database lock, without touching any SQLite file, before changing code.
$locks=@()
try {
    $private=Join-Path $target '.private'
    if (Test-Path -LiteralPath $private) {
        foreach ($file in Get-ChildItem -LiteralPath $private -Filter '*.lock' -File -Recurse) {
            $handle=[IO.File]::Open($file.FullName,'Open','ReadWrite','ReadWrite')
            $locks+=,$handle
            try { $handle.Lock(0,1) } catch { throw 'Close workspace in the dashboard before upgrading.' }
        }
    }
    if ($previous) { throw 'Managed workspace already exists. Use scripts/update-workspace.py from the reviewed staging package, with user approval and a verified backup; this first-install helper cannot overwrite installed code.' }
    foreach ($file in $files) {
        $relative=$file.FullName.Substring($source.Length+1)
        $path=Safe-Target $relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $path) -Force | Out-Null
        Copy-Item -LiteralPath $file.FullName -Destination $path -Force
    }
    if ($previous) {
        foreach ($property in $previous.files.PSObject.Properties) {
            if (-not $hashes.ContainsKey($property.Name)) { Remove-Item -LiteralPath (Safe-Target $property.Name) }
        }
    }
    New-Item -ItemType Directory -Path $private -Force | Out-Null
    [IO.File]::WriteAllText($manifestPath,(@{revision=$Revision;files=$hashes} | ConvertTo-Json -Depth 4),[Text.UTF8Encoding]::new($false))
    [pscustomobject]@{installed=$true; upgraded=[bool]$previous; source_files=$files.Count; private_data_preserved=$true; revision=$Revision} | ConvertTo-Json -Compress
} finally { foreach ($handle in $locks) { $handle.Dispose() } }
