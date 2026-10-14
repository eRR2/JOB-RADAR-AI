# JOB-RADAR AI — weekly career research

A private Windows browser workspace for finding credible next-career opportunities
from demonstrated experience and the user's original goals. Subscription Codex or
Claude Code CLIs provide analysis; Python validates evidence, protects source access
and persists history. No API-key fallback or automatic applications.

Development branch: `codex/weekly-research-rebuild`. Main remains the existing
release. This branch is a preview, not a verified stable release.

## Current workflow

Upload a readable PDF/DOCX CV, describe the next move and explicitly allow private
AI processing and anonymous public research. Direct LinkedIn guest requests require
separate consent. The existing private-runtime launcher is documented in
[installation](docs/INSTALL_CODEX_DESKTOP.md).

The current coordinator is `SessionSearch`:

1. Start a verified, backed-up search session while preserving durable history.
2. Use explicit role intent for transport seeds; create or reuse a private anonymous
   capability brief before public web research. Raw career text and CV experience
   records do not enter web-enabled inference.
3. Discover actual observed vacancies using indexed LinkedIn, public web and employer
   publications. Source access failures remain uncertainty, not proof of closure.
4. Match exact employer requisitions, source identities and normalized URLs. Matching
   without IDs requires corroborating employer, title, location and substantial content.
5. Exclude already applied/rejected exact vacancies from expensive review. Privately
   triage other candidates before bounded description enrichment and assessment.
6. Show fresh credible recommendations first, with a short separate section for
   previously found opportunities. All Opportunities retains other discoveries.

Incomplete assessments have a separate section and an explicit timeout, budget or
validation reason. Source-confirmed closed positions remain visible as review
exclusions; they are not cached assessments. Completed phase labels reflect actual
coverage. Snippet-only decisions stay short and preliminary. Final recommendations
require a verified publisher description and literal responsibility evidence. Primary
discovery covers each selected market once, then compact relevance triage orders source
verification before bounded assessment calls of at most two complete descriptions.
Broader discovery avenues are recorded as deferred, not exhausted. Missing source text
remains pending; budgets and provider failures never imply completed assessment.
The 5.3 preview also refuses the `--scheduled` CLI entry before opening storage or
providers. Searches require an explicit dashboard action; legacy catch-up remains
tested separately against its V2 contract.
Publication-title hints
for employer, locality and advertised compensation are labeled unverified and never
replace canonical identity facts. An advertised salary ceiling is not guaranteed pay.
An empty local application status is unverified until supported by a recorded decision.
Dutch employer-ruling information is shown only for roles identified as Dutch.

Every recommendation explains fit, gaps, technical versus disciplinary authority and
trade-offs. Qualitative priority is separate from evidence completeness. Salary, hours
and workplace terms require literal source evidence. Employer ruling support requires
a source quotation; personal tax eligibility remains unverified. Salary, title and
location preferences do not impose universal hard exclusions.

Current results, query caches and run diagnostics are disposable. CV/goals, explicit
feedback, vacancy identities, saved/application/rejection decisions, event timelines
and imported mailbox evidence survive searches. Same-company different roles remain
independent. Manual corrections are not overwritten by repeated mailbox imports.

## Outlook evidence

The application currently imports a user-selected read-only JSON export from the
Outlook **Job Radar** folder. It does not connect to Outlook automatically, send mail
or execute email instructions. Ambiguous evidence remains unresolved. Requisition
matches require corroborating employer text. This conservative matcher is a baseline,
not a complete multilingual mailbox parser.

## Offline verification

Run the full Python suite from the repository:

```powershell
python -m unittest discover -s tests -v
node --test tests/web_clean.test.cjs
node --check web/app.js
python -m compileall -q job_radar_ai scripts tests
python scripts/check_privacy.py
```

Run the attributed LinkedIn integration from its own directory with Bun on PATH:

```powershell
Set-Location integrations/linkedin/cli
bun test --timeout 30000
```

Current foundation checks are `test_imports.py`, `test_foundation.py`,
`test_research_privacy.py`, `test_http_offline.py`, `test_weekly_method.py`,
`test_clean_search.py` and `test_discovery_first.py`.
In-memory HTTP tests supplement real loopback tests; DOM fixtures do not prove visual
browser behavior. Earlier UI tests describe superseded multi-tab contracts and remain
visible as historical material.

Findings, exact verification outcomes, remaining architectural issues and release
limits: [foundation audit](docs/FOUNDATION_AUDIT.md). No live AI or publisher research
was used for this stabilization. Do not interpret offline passes as proof of live
model quality, source availability or a clean second-PC installation.

## Scope and privacy

One loopback process, local SQLite, native browser UI and bounded CLI/source workers.
No added framework, cloud backend, arbitrary model shell commands, automatic retries,
provider fallback, automatic schedule or individual per-job AI description loop.
Active robots/authentication/explicit publisher denials and unexpired publisher
Retry-After restrictions survive sessions.

MIT attribution is preserved. Private data, runtime, backups and verification fixtures
stay outside Git under `.private/`; provider-owned authentication remains with the
provider. A stable release or GitHub write requires an explicit owner request.

