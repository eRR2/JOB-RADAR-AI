# JOB-RADAR AI V5

A local AI career researcher using your existing Codex subscription. Upload your CV,
describe your next move in one text box, review the AI understanding and begin research.
No universal profession, employers or countries. LinkedIn indexed vacancy discovery is
the first focus; employer careers and other useful public sources remain available.

V5 preview lives on [`feat/v5-ai-career-research`](https://github.com/eRR2/JOB-RADAR-AI/tree/feat/v5-ai-career-research).
Main still contains V1. No stable V5 Release, hosted service, API key or automatic applications.

## Start in Codex Desktop on Windows

Copy this into Codex Desktop:

> Review https://github.com/eRR2/JOB-RADAR-AI/tree/feat/v5-ai-career-research and prepare
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
Indexed links and snippets stay preliminary until exact full-description retrieval and
evidence-based ATS/HR evaluation. Partial progress is retained; no tiny country-split quota.

Recommended, All Opportunities, dynamic country tabs, Applications and Reports retain
observed vacancies, preliminary perspectives, source evidence, full evaluations and
application history. Feedback belongs to the verified vacancy country; unknown locations
stay unclassified. No Global/Scope/Required preference forms or country-code editing.

Direct LinkedIn description access is separate, optional and consented. HTTP 429 respects
Retry-After or finite backoff; active restrictions are never retried or bypassed. Other
publisher denials remain authoritative. A direct-access failure does not stop indexed
web discovery. No proxies, credentials, stealth or alternate denied endpoints.

Set a manual/daily/weekly routine. Skill mode offers Run now / Remind later / Skip when
reopened; no Windows scheduled task or research while the PC is off.
User data lives only under ignored `.private/`; real private data is never shipped.

## Current verification limits

Real Codex search events found indexed LinkedIn vacancies, and the synthetic-profile
V5 acceptance run retained Appical's Engineering Manager (People Lead) with a genuine
preliminary management-progression assessment. It did not obtain a full description
or prove vacancy openness. Full-description evaluation is fixture-tested.
Claude web discovery, clean Windows VM setup and complete visual/accessibility QA remain
unverified. Read [the precise acceptance evidence](docs/V5.md); passing tests alone is
not a claim of complete market coverage.

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
