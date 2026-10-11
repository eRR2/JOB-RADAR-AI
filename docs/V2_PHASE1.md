# V2 Phase 1: skill launch and persistent local AI bridge

## Scope and decision

Build the requested onboarding → AI plan → bounded upstream search → full-text
assessment → browser result → feedback → restart path in the existing independent
repository. Keep V1 recoverable in Git and through its original entrypoints.
No publication, hosting, native scheduler, credentials, automatic applications
or change to the older JOB-RADAR repository.

| Alternative | Prerequisites and work | Decision |
| --- | --- | --- |
| Bun/Node local JavaScript bridge | Runtime download still needed; rewrite or wrap SQLite, CV parsing, provider isolation and upstream safety | Adds a second bridge or substantial regression surface; defer |
| Browser-only storage/static dashboard | Browser available, but current AI subprocess cannot reliably share IndexedDB | Does not satisfy persistent two-way AI bridge |
| Private uv-managed Python + existing loopback app | Small Windows launch script; reuse tested storage, guarded APIs, parser, AI and upstream CLI | Selected, fewest new boundaries |
| Bundled/frozen executable | Signed per-platform release artifacts and a build/distribution pipeline | Potential future distribution; unnecessary for this slice |

No JavaScript framework, frontend build, paid API or host service is needed.
Python still performs validation/transport/persistence. All career interpretation,
query generation, selection, ATS/HR assessment and feedback learning remain AI-owned.

## Real data path and execution boundaries

The invoking local agent executes `scripts/launch-skill.ps1`. PowerShell starts
a hidden `python -m job_radar_ai --skill-mode --no-browser` child, waits for a
loopback health response matching the checkout and database, then opens the
default browser. Neither a launcher exit nor CLI presence proves AI inference.
The browser displays actual application state, not an embedded static mockup.

Browser onboarding and feedback → Host/Origin/CSRF guarded HTTP → ignored
`.private/state.sqlite3` → restricted subscription AI subprocess prompts → validated
plan/evidence/report → same database → browser polling. `Store.feedback()` supplies
persisted feedback to the next AI run, including IDs and associated job context.
The invoking chat and dashboard's AI are separate sessions; there is no assumed
ability to inject browser input into a currently open Codex/Claude chat.

The default database path stays unchanged; no private database is migrated or
replaced. Synthetic verification uses explicitly named private databases, never
to escape a source stop. Stable source identities, persisted running-run uniqueness,
process locks and source budgets/cache/stops continue to protect the workflow.
Job/CV/model text is data; existing AI subprocess tool restrictions and exact
quote/identity checks remain in force. No model-generated shell commands.

In skill mode, the server has no scheduler thread. Daily/weekly preferences expose
only the latest due local slot, including a missed weekly day. Run now consumes
the slot only after a real run starts; Remind later persists a one-hour deferral;
Skip records a skipped run. Manual Search with AI consumes the current slot too.
No backlog replay, OS task or automatic search while the UI/runtime is closed.
Close workspace stops the loopback process after active operations finish.
Existing V1 native tasks, if any, must be managed separately; skill mode cannot
create one. Legacy V1 launchers retain legacy scheduling behavior.

## Runtime/bootstrap and clean Windows

Current `.venv` and Bun can be reused. Missing prerequisites produce an explicit
approval-required response before download. Approval permits fixed runtime ZIPs
from the official uv/Bun GitHub releases, checked against SHA-256 values recorded
in `scripts/runtime-manifest.json`, uv-managed Python 3.13.7, and locked binary
Python dependencies. Downloads, Python, virtual environment, cache and temporary
files stay under `.private/runtime`. Python comes from uv's
python-build-standalone distribution, not a python.org installer.

No admin installation, permanent PATH/registry edits, provider credential access
or downloaded-script evaluation. A PowerShell execution-policy override is scoped
to the single child process; organization-enforced restrictions must not be changed.
Windows x64 and Internet access to GitHub/Python package sources are required.
The exact pinned ZIP digests come from official release asset metadata.

**Codex installed alone is not sufficient evidence on a clean PC.** The calling
environment needs local shell/files/process/network/default-browser capabilities,
PowerShell, and the dashboard needs a separately usable, subscription-authenticated
Codex CLI executable. A desktop/IDE app's internal runtime or login is not a
documented public CLI/runtime guarantee. Bun and Python do not require *manual*
installation when approved bootstrap succeeds, but both are real runtime dependencies.
Do not claim universal zero-install support.

The canonical skill and repository adapters contain the launch workflow and shared
execution boundaries. Copying only a skill folder does not distribute the app.
A full checkout or future reviewed release archive is still required. This feature
branch has not been published; GitHub main installation does not yet provide V2.
Claude's project skill convention is prepared; live launch/inference must stay
unverified when Claude Code is absent. A clean Windows VM remains a separate test
from forcing private runtimes on this already-provisioned machine.

## Official references

- [Codex skills](https://developers.openai.com/codex/skills/): repository skills are instructions executed by the agent, not a server runtime.
- [Claude Code skills](https://code.claude.com/docs/en/skills): project `.claude/skills` and explicit `/job-radar-ai` convention.
- [uv managed Python](https://docs.astral.sh/uv/guides/install-python/) and [environment settings](https://docs.astral.sh/uv/reference/environment/): private Python/cache locations and registry controls.
- [Bun installation](https://bun.sh/docs/installation): standalone executable, Windows prerequisites and official binary release downloads.
- [Pinned uv release](https://github.com/astral-sh/uv/releases/tag/0.9.5) and [pinned Bun release](https://github.com/oven-sh/bun/releases/tag/bun-v1.3.14).

## Acceptance evidence

Verified on the current Windows x64 machine on 2026-10-12 (Europe/Berlin), using a
fictional CV and public source results. No user CV was sent for verification.
Private raw evidence stays in ignored `.private/verification` and the isolated
SQLite databases. The default user database was not used for onboarding/search.

| Acceptance | Observed evidence |
| --- | --- |
| A: Codex skill | Actual app-server `skills/list` returns `job-radar-ai`, enabled, repo scope; real Codex CLI `$job-radar-ai` invocation executed the fixed launcher and returned ready/skill-mode/browser-requested true, exit 0 |
| B: real browser | Fixed skill launcher returns matching health identity; Chrome window has JOB-RADAR title; user confirmed dashboard opened |
| C/D: onboarding and persistence | Actual guarded CV upload parser and profile API saved synthetic CV, location, weights and daily frequency; subscription AI interpreted and accepted the profile |
| E: AI-selected upstream search | Codex generated a plan; upstream tool searched its query in Berlin, Germany; 10 actual job cards, 2 source requests total |
| F/G: full description and reasoning | One actual full description retrieved and AI-evaluated; completed run, no warnings; user saw the dashboard and saved Like actions |
| H: browser feedback to later AI | 3 Like records from browser persisted; next successful AI reassessment loaded `Store.feedback()` into its prompt context and used the stored description, with 0 new source requests |
| I: restart | Close endpoint stopped the server, then managed-runtime launch reopened the same database; exact hash of CV/profile/jobs/runs/learning before/after was identical (10 jobs, 3 feedback records, 2 completed runs) |
| catch-up | Tests cover missed weekly days, daily-before-time catch-up, persisted reminders, skip, stale/duplicate actions and failed/valid Run now; skill mode has no scheduler thread and rejects native tasks |
| V1 recovery | Original launchers and attribution retained; main remains at `fba8f7c43f49afcd710c734600ca8f7884cc90a6`; no merge or publication |

Bootstrap was explicitly approved by the user. `-ManagedOnly -ApproveBootstrap`
downloaded verified uv/Bun ZIPs, privately provisioned Python 3.13.7 and all six
locked Python packages, and successfully served a second private workspace.
`-ManagedOnly -Check` now reports Python/Bun ready and bootstrap not required.
Restart of the live search workspace then used only these managed runtimes.
This proves the private bootstrap path on this machine while excluding existing
project/user Python/Bun; it does **not** constitute a clean Windows VM test.

The baseline had 52 passing Python tests. Final validation includes 63 Python
behavior/integration tests, 74 upstream Bun tests using private Bun 1.3.14,
`node --check web/app.js`, staged privacy/history/ignore scanning, and human diff
review. An inverted catch-up consumed-slot condition was detected by the tests
and restored. An incomplete existing Python environment was reproduced as a
failing prerequisite-probe test and fixed without silent installation.

Browser automation surfaces were unavailable in this session; real opening and
feedback clicks were verified by the user plus persisted HTTP/SQLite evidence.
Automated visual/keyboard/accessibility QA, clean Windows VM, live Claude and
standalone GitHub V2 distribution remain unverified/unreleased. No claim that
current-chat memory itself receives feedback: the next dashboard AI subprocess
loads it from the same private database. No extra LinkedIn search was needed for
feedback or restart verification.
