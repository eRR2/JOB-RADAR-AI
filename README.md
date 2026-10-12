# JOB-RADAR AI V5.1

A local AI career researcher using your existing Codex subscription. Upload your CV,
describe your next move in one text box, choose Search with AI. Interpretation is internal; no compulsory summary approval.
No universal profession, employers or countries. LinkedIn indexed vacancy discovery is
the first focus; employer careers and other useful public sources remain available.

V5 preview lives on [`feat/v5-1-research-completion`](https://github.com/eRR2/JOB-RADAR-AI/tree/feat/v5-1-research-completion).
Main still contains V1. No stable V5 Release, hosted service, API key or automatic applications.

## Start in Codex Desktop on Windows

Copy this into Codex Desktop:

> Review https://github.com/eRR2/JOB-RADAR-AI/tree/feat/v5-1-research-completion and prepare
> a new private Windows workspace from a reviewed exact revision. Register the bundled
> job-radar-ai skill and open the dashboard. Ask before missing private runtime/CLI
> downloads; help me use my own subscription login. Do not reuse another user's data
> or replace an existing installation. I will upload my CV and describe my next move.

No VS Code or manual Python/Bun installation. Private pinned runtime/bootstrap and
the separate Codex CLI require download consent when missing. Desktop login alone
does not prove CLI authentication, inference or web research.
See [setup](docs/INSTALL_CODEX_DESKTOP.md) and [V5 implementation/evidence/limits](docs/V5.md).

In an existing reviewed V5 checkout, invoke `$job-radar-ai`; Codex launches the same
loopback dashboard automatically. Existing V5 CV/history persist on restart and upgrades.
Historical V1–V4.1 databases are refused, never silently migrated/imported or restored.
An old installation needs a separately authorized fresh start or a separate new workspace.

## Research and workspace

AI conducts actual public web research in meaningful, cancelable batches, within a
fifteen-minute run window and provider/source limits. Raw CV is excluded from web-enabled
discovery: private inference first produces an anonymous professional research brief.
Source observations establish URLs/facts; model prose cannot create retrieved text.
Promising — Needs Verification makes useful snippet-supported leads visible. Targeted follow-up investigates retained vacancies without another discovery run. Indexed links stay preliminary until exact full-description retrieval and
evidence-based ATS/HR evaluation. Partial progress is retained; no tiny country-split quota.

Recommended, All Opportunities, dynamic country tabs, Applications and Reports retain
observed vacancies, preliminary perspectives, source evidence, full evaluations and
application history. Geography distinguishes verified, inferred and unknown; strong city mappings permit country-view visibility without verified-country learning. Feedback belongs to the verified vacancy country; unknown or inferred locations
stay unclassified. No Global/Scope/Required preference forms or country-code editing.

Direct LinkedIn description access is separate, optional and consented. HTTP 429 respects
Retry-After or finite backoff; active restrictions are never retried or bypassed. Other
publisher denials remain authoritative. A direct-access failure does not stop indexed
web discovery. No proxies, credentials, stealth or alternate denied endpoints.

Set a manual/daily/weekly routine. Skill mode offers Run now / Remind later / Skip when
reopened; no Windows scheduled task or research while the PC is off.
User data lives only under ignored `.private/`; real private data is never shipped.

## Current verification

V5.1 preserved the developer's 38 V5 vacancies, CV, original career text, feedback,
application history and original report. Actual targeted work recovered and evaluated
one German Saab and one Dutch Sioux posting; two full descriptions, two full AI
assessments, zero forced recommendations. Other useful preliminary leads remain visible.
Native Codex page opening was verified. Full text is checked with controlled publisher
retrieval because CLI event metadata does not export the complete native page body.
Source 404/410, uncertain availability and provider failures remain accurately labeled.
See [V5.1 evidence and limitations](docs/V5_1.md). Browser automation still cannot verify
localhost visually, and a clean Windows VM / Claude web tools remain unverified.

## Development

Use the project's `.venv\Scripts\python.exe` for Python checks and place the existing
Bun directory on the test process PATH for its child-process fixtures. Run focused
behavior checks for the change, `node --check web/app.js`, the offline Bun parser/CLI
tests and `scripts/check_privacy.py` with the project interpreter after staging.
See [architecture](docs/ARCHITECTURE.md), [actual V5 evidence](docs/V5.md) and
[tasks](tasks/todo.md). No npm frontend runtime dependency was introduced.

The original V1–V4.1 source history remains in prior branches for code rollback;
it is not an invitation to restore historical user data into V5.
MIT licensed; [third-party notices](THIRD_PARTY_NOTICES.md) retain upstream rights.
