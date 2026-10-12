# V5 launch and second-user setup

For first-time Windows Codex Desktop setup and safe upgrades, follow
`docs/INSTALL_CODEX_DESKTOP.md` in the checkout. Codex downloads/reviews a public
source archive, installs a new user workspace with `scripts/install-workspace.ps1`,
and registers its exact path with `scripts/register-skill.ps1` using the documented
user skills directory. No VS Code or manual CMD/Python command is required.
Missing Codex CLI has a separate approval-gated private release ZIP helper,
`scripts/setup-codex.ps1`; login uses the official CLI browser flow. Desktop
login, CLI login status and actual inference remain separately verified.

The repository adapters are recognized in `.agents/skills/job-radar-ai` (Codex)
and `.claude/skills/job-radar-ai` (Claude Code). Invoke `$job-radar-ai` or
`/job-radar-ai` in this checkout. The calling agent executes the fixed launch
script, rather than asking the user to use the old CMD/Python launcher.

`scripts/launch-skill.ps1 -Check` is a read-only local prerequisite probe.
The normal launcher reuses healthy `.venv` / private runtime Python and Bun on
PATH or `~/.bun/bin`. It starts the loopback server with `--skill-mode`, verifies
the checkout/database identity, and requests the default browser to open.
Already-running V5 in that same workspace is reused. An unrelated service or
V1 server is never stopped or mistaken for successful V5 startup.

If missing, ask for approval to download pinned uv 0.9.5, managed Python 3.13.7,
locked Python wheels and Bun 1.3.14 into `.private/runtime`. Then pass
`-ApproveBootstrap`. The ZIPs have source-controlled SHA-256 digests from the
official releases. Python is supplied by uv's python-build-standalone distribution;
it is not an official python.org binary. No downloaded script is evaluated.
No registry registration, permanent PATH edits, admin privileges or OS task.
Downloads require Internet and may be blocked by organizational policy. Never
override such denial. Windows x64 is the supported bootstrap target for Phase 1.

The calling agent needs a supported local shell, file/process/network permission,
PowerShell and default-browser access. The dashboard AI additionally requires an
installed, subscription-authenticated **Codex CLI** or **Claude Code CLI**. A Codex
desktop/IDE installation alone does not prove that CLI prerequisite. The existing
adapter discovers direct native executables; no credential export or API key is
used. The calling agent and dashboard AI subprocess are separate sessions; there
is no undocumented injection into the current chat.

For verification only, `-ManagedOnly` ignores existing `.venv` and user Bun,
`-Database .private/v5-verification.sqlite3 -Port 8768` isolates synthetic data,
and `-NoBrowser` skips the browser-open request. These are developer options.
Do not silently choose a fresh database to evade a source stop. Once LinkedIn
denies access, no retries, resets or substitute routes for that verification.

Copying only this skill package elsewhere does not ship the app. A full repository
checkout or reviewed public source archive remains necessary. V5 is on
`feat/v5-ai-career-research`: GitHub main does not contain these changes.
Claude invocation conventions are documented, but live
execution needs Claude installed. See `docs/V5.md` in the checkout for
runtime decisions, clean-machine limits and current evidence.

V5 fresh storage is generation 5: do not import old CV/history/stops. Existing V5 data
is preserved. See docs/V5.md for developer reset evidence and preview limitations.
