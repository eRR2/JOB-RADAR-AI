# A local instruction-only skill in Codex's documented user skills directory.
[CmdletBinding()]
param([string]$SkillsDirectory = (Join-Path $env:USERPROFILE '.agents/skills'))
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if (-not (Test-Path -LiteralPath (Join-Path $root 'skills/job-radar-ai/SKILL.md'))) { throw 'Application checkout is incomplete.' }
if ($root.Contains('`') -or $root.Contains("`n") -or $root.Contains("`r")) { throw 'Unsupported checkout path.' }
$destination = Join-Path $SkillsDirectory 'job-radar-ai'
$canonical = (Join-Path $root 'skills/job-radar-ai/SKILL.md').Replace('\','/')
$text = @"
---
name: job-radar-ai
description: Launch and operate my private JOB-RADAR AI career dashboard; use my existing checkout and preserve its CV, database and history.
---

Read the [canonical skill](<$canonical>) and follow it.
The application checkout is $root. Run its fixed scripts/launch-skill.ps1 automatically.
Never replace the checkout, create another database, copy credentials or run a remote script.
Private runtime/provider downloads require explicit consent. Never change unrelated skills.
"@
if (Test-Path -LiteralPath $destination) {
    $file = Join-Path $destination 'SKILL.md'
    if (-not (Test-Path -LiteralPath $file) -or (Get-Content -LiteralPath $file -Raw).TrimEnd() -ne $text.TrimEnd()) { throw 'An existing job-radar-ai skill belongs to another installation. Preserve it; use this checkout as a Codex project instead.' }
} else {
    New-Item -ItemType Directory -Path $destination | Out-Null
    [IO.File]::WriteAllText((Join-Path $destination 'SKILL.md'),$text,[Text.UTF8Encoding]::new($false))
}
[pscustomobject]@{registered=$true; scope='user'; overwrite=$false; restart_if_not_visible=$true} | ConvertTo-Json -Compress
