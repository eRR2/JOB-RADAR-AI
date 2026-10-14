# Weekly research foundation audit

Reviewed source: `eRR2/JOB-RADAR-AI`, branch `codex/weekly-research-rebuild`,
commit `96e3aa9bbe374d594abaf310a03f108fde2a6f80` (14 October 2026).
The implementation was prepared in an isolated local review checkout. The audit and
offline verification did not modify GitHub branches, releases, real CVs, mailboxes
or an existing user database. The owner subsequently authorized publication of this
review package only to `codex/weekly-research-rebuild`; main and releases stay unchanged.
No live model inference or publisher research was run.

## Outcome

The source snapshot could not import its active coordinator. The offline foundation
now compiles and passes the current workflow, identity/history, privacy, evidence,
handler and cancellation regressions. It is ready for code review, not a stable
release certification. Real loopback/browser and clean-machine checks remain open.

## Confirmed problems and corrections

| Severity | Original behavior | Correction and evidence |
|---|---|---|
| P0 | `session_search.py:468` contained an unmatched expression followed by a second coordinator implementation; the app failed with SyntaxError. | Remove the corrupted duplicate block. AST regression checks every runtime module and duplicate top-level definitions. |
| P1 | An email containing another company's identical requisition number could reject the wrong vacancy. | Require employer corroboration and exact requisition boundaries; ambiguous title/company records stay unresolved. Test both import-after-discovery and import-before-discovery. |
| P1 | New searches deleted the application event timeline; saved state and mailbox provenance could be lost or relabeled manual. | Add durable `history_application_events`, archive existing events before reset, preserve status/source and expose durable histories in export. |
| P1 | Reimporting old mail or rediscovering a vacancy could undo a manual correction. | Idempotent evidence import; honor manual status provenance, including explicit clears. |
| P1 | Source-ID/title heuristics could incorrectly merge distinct same-title jobs or treat a republished employer requisition as new. | Same employer + explicit requisition takes precedence. Otherwise use exact source/normalized URL, or employer/title/location plus substantial corroborating content. Missing content cannot prove identity. |
| P1 | Discovered employer requisitions were not carried through the active observation pipeline. | Retain only source-corroborated requisitions and carry official recovery IDs forward. No substitution of LinkedIn IDs for employer requisitions. |
| P1 | Original private career text and CV-derived experience records entered web-enabled inference; the anonymous capability cache was never populated. | Privately create and cache the existing anonymous brief contract. Web context excludes original goals and CV experience records; uninterpreted prose cannot seed direct transport. Synthetic privacy tests inspect every public-call context. |
| P1 | Invalid reassessment could leave an older `recommend=true` decision active. Partial page evidence was labeled but omitted from assessor context/quote validation. | Withhold only the affected recommendation; use partial text in bounded context and literal evidence validation. UI also rejects invalidated decisions. |
| P1 | The presence of the word ruling could be shown as employer support, including an explicit refusal. | Require a literal `ruling_quote` before displaying a support/refusal claim; distinguish employer support from unverified personal eligibility. Semantic interpretation remains an AI assessment, with the quote visible for review. |
| P1 | Windows cancellation depended entirely on taskkill; denial left an owned child running and `wait()` timed out. | Attempt bounded tree termination, then terminate the owned child handle when necessary. Real synthetic cancellation tests pass with tree termination deliberately denied. |
| P2 | Previously seen opportunities still occupied the main recommendations grid; collected hours/workplace evidence was not rendered; qualitative priority was hidden. | Put fresh recommendations first and rediscoveries in a short separate section. Display priority, source hours/workplace terms, authority, gaps and trade-offs. |
| P2 | README and architecture still described disposable application history and an obsolete branch contract. Historical fixtures lacked the public-fetcher budget/schema or expected an empty source result despite a fabricated supplementary result. | Update current documentation and correct those fixtures without relaxing production validation. Legacy false-source and partial-result checks remain. |

No new scoring formula, framework, hosted service, dependency, provider fallback,
automatic schedule or per-vacancy AI description loop was added. Roughly 400 lines
of duplicate coordinator code were removed. Historical coordinators were not broadly
deleted: old-version paths still reference them, and removing them would be a separate
compatibility change rather than a safe baseline fix.

## System review scope

| Boundary | Reviewed behavior / limits |
|---|---|
| Launch/install/update | Private runtime, workspace/process locks, preview version routing, path/inventory checks and recoverable code replacement. Installation/update regressions were included in the full suite. No bootstrap download, update or release executed. |
| CV/intent | Local bounded PDF/DOCX extraction, contact redaction, strict structured intent with source quotes, current-CV reuse and market scope. No real CV needed for implementation. |
| Discovery/orchestration | Actual native observations, fair market passes, source restrictions, phase/call budgets, partial-result retention, triage before enrichment and private assessment. Applied/rejected roles are retained but excluded from costly current review. |
| Source transport | LinkedIn adapter plus robots-aware pinned HTTPS and official posting recovery; fetched evidence and snippet/page completeness remain distinct. Unknown access/openness is not closure. |
| Identity/state | Current session token, verified backup, late-worker refusal, durable identities/application events/mail evidence, explicit feedback and private export. Conservative ID-less matching trades some false negatives for avoiding wrong rejections. |
| AI contracts | No shell/MCP tools in provider inference, no API-key fallback, source/CV literal quotes, individual invalid assessments withheld, scoped feedback and cancellation. Anonymous summarization and semantic interpretation still require future live-quality verification. |
| HTTP/UI | Loopback Host/Origin/CSRF guards, asset allowlist, escaped text/HTTPS links, fresh/revisited sections, source terms, status actions and lower-relevance discoveries. In-memory handler and DOM tests pass; actual browser appearance is unverified. |
| Historical features | V1/V5 coordinators, scheduler, individual description resolver and old multi-tab UI expectations are not the active 5.3 workflow. Their presence makes the full suite larger than the current product contract. |

## Verification

All data was synthetic and all research/provider boundaries were stubbed or restricted.
Pinned dependencies were available from the local package cache; no downloads were made.

| Check | Result |
|---|---|
| Current foundation + provider + legacy orchestration regressions | **63 passed**, no skips |
| Current browser DOM behavior (`web_clean.test.cjs`) | **10 passed**, no skips |
| Attributed LinkedIn integration, executed from its own directory with Bun on PATH | **77 passed**, no skips |
| Python runtime/scripts/tests compilation, JavaScript syntax and Git whitespace | Passed |
| Staged privacy audit | Passed: 134 indexed files, local Git history and eight private-path ignore probes; source/prose reviewed |
| Review patch | Original content verified against 19 GitHub blob SHAs; patch application checked against the exact reviewed source |
| Mutation check: temporarily remove employer corroboration | Two regressions failed as expected; implementation restored |
| Full Python discovery | **253 run; 1 failure and 31 error records**. Not an all-green result. |
| Full-suite remaining error records | Loopback HTTP clients refused by this execution environment with WinError 10013. The two-route subtest yields two records. No tests were disabled. |
| Full-suite remaining failure | Managed-runtime first-launch fixture returned `BOOTSTRAP_APPROVAL_REQUIRED` because this isolated checkout lacks the managed runtime. No download was approved or attempted. |
| In-memory real handler coverage | Origin/Host/CSRF, selected-folder import/export, stale-worker/search reset and private/removed routes passed. This does not certify real network transport. |
| Browser visual/console/accessibility QA | Attempted but unavailable: browser automation kernel could not locate a Windows platform directory. Synthetic server was stopped afterward. |
| Live AI/provider quality and publisher coverage | Intentionally not run; no claim about real recommendations or latency |

Reproduce the current Python gate from the repository:

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'tests')
python -m unittest test_imports test_foundation test_research_privacy test_http_offline test_weekly_method test_clean_search test_discovery_first test_providers test_orchestration -v
```

The full command remains `python -m unittest discover -s tests -v`.
Use installed locked Python dependencies and a writable temporary directory. Tests
require loopback networking for transport integration, and the launcher smoke test
requires the reviewed managed runtime. Do not lower the suite or silently mark those
checks successful because the current environment cannot satisfy prerequisites.

## Remaining architectural issues and release gates

1. **Actual UI/transport and installation:** rerun loopback integration, first launch,
   navigation/status/import actions, cancellation and restart on a normal Windows test
   environment with the managed runtime. These are release gates.
2. **History growth:** `match_history` scans the full catalogue, and `jobs()` now reads
   durable events for each match. Work grows with current-results × historical-records;
   weekly backup copies also grow indefinitely. No large-history benchmark or retention
   policy was established. Measure before adding indexing or automatic deletion.
3. **Mailbox coverage:** the read-only JSON importer is not a live Outlook integration.
   English/German acknowledgement/rejection patterns and conservative text identities
   do not cover every Dutch/forwarded/HTML message. Ambiguous records require review;
   title-only evidence before future competing roles cannot guarantee perfect identity.
4. **Data erasure:** the existing `/api/erase` route deletes selected named backup
   patterns but does not include `before-search-*.sqlite3` snapshots. Do not claim that
   this action removes every private backup. Correct that lifecycle in a separate
   confirmed deletion-path change with route regressions before a stable release.
5. **Source breadth and budget:** at most two indexed passes per market and 16 AI calls
   keep research bounded, but do not prove comprehensive employer coverage. Provider
   schema fields are required; legacy saved-record validation permits omitted additions.
   Salary/authority/ruling completeness and
   domain-fit quality need a later explicitly authorized live acceptance run.
6. **Process trees and alternate provider:** the Windows fallback terminates the owned
   child when taskkill is denied; it does not prove every descendant process is contained.
   Claude currently lacks the same native web-observation trace and cannot be advertised
   as equally verified public discovery. No permission bypass was introduced.
7. **Legacy separation:** version-dependent server imports keep earlier coordinators
   and tests reachable. `web_market.test.cjs` still expects superseded controls and is
   not the current UI contract. Consolidating legacy modules/archived test organization
   should follow a deliberate compatibility decision, not another rapid rewrite.

No recommendation is made to merge main, publish a stable release or start live
research until the applicable gates are addressed and the owner explicitly requests it.

## Provider schema diagnosis (14 October 2026, local follow-up)

Baseline: `codex/weekly-research-rebuild`, `2b0c3f7`. The running VS Code-launched
application's PATH selects the npm package's native Codex executable, version
**0.161.0**. `login status` reports ChatGPT subscription authentication; `exec --help`
includes the adapter's options. The agent terminal's PATH selects a different bundled
CLI, so that terminal alone would not establish the application's selection.

The actual outbound schemas violated strict Structured Outputs: `research_v5` job
items omitted `requisition_id` from `required`; `priority_v52` assessment items omitted
eight added findings. Offline request-boundary regressions failed on both providers
before correction. OpenAI's [Structured Outputs contract](https://developers.openai.com/api/docs/guides/structured-outputs)
requires every object property in `required`, including nested array items, and
`additionalProperties: false`.

`provider_schema()` now builds a separate strict copy for both CLI requests. Local
validation retains optional additions for old records, all original types/limits and
source quotation checks. Missing evidence remains empty/unknown/unverified, rather
than invented. No database migration or user-data update is needed.

`execution_error()` now preserves the exit code and allowlisted HTTP/error codes,
schema paths and missing contract field names. It consumes error events from JSONL
without treating model messages as errors. It never returns or logs raw CLI output,
CVs, prompts, contacts or credentials. The existing fatal execution-error category
is preserved so schema rejection does not start another market's provider call.

No live inference or publisher requests were made. The earlier failure's raw
stderr/stdout was discarded by the old adapter and cannot be reconstructed from its
generic message. HTTP 400/schema-error fixtures are synthetic; the schema defect is
verified offline, while a live end-to-end success is not claimed.

The full Python run executed **259 tests: 253 passed, 1 failure, 5 errors**, no skips.
The five legacy catch-up errors reproduce with original HEAD provider/contract
modules loaded in memory. The launcher fixture fails because the already-running
workspace holds its update lock, as confirmed by that synthetic launch's stderr.
No locks were bypassed or existing dashboard stopped. Final focused verification
passed **89 tests**, including seven new provider regressions covering every outbound
nested schema for both CLIs, safe error diagnostics and legacy compatibility.

## Review completeness follow-up (14 October 2026)

The bounded evaluation coordinator could label an unfinished evaluation phase complete,
count closed jobs as cached decisions, and continue further assessment calls after a
provider timeout. It lacked persistent per-vacancy reasons for unassessed candidates.
Evaluation now advances in one eight-job batch per market turn, retains each successful
batch, stops provider calls on failure, records pending/excluded/invalid decisions and
marks outstanding assessment coverage partial. Missing full descriptions also produce a
source-limited partial result. Source-enrichment attempts retain access/identity failure
reasons for future diagnostics instead of only a generic description status.

The state response projects reasons from legacy run diagnostics without changing their
stored assessments or source facts. Title-derived company/locality/compensation hints
carry the observed title, URL and unverified state separately from canonical identity
fields. Application-history matching remains exact and local-only; legacy/default
`none` is not proof of no application. Explicit confirmations persist independently
of that default. No mailbox was fetched or imported for this diagnosis.

The main report separates fresh reasoned opportunities, short previously found leads,
incomplete assessments and explicit exclusions. All Opportunities retains lower-relevance
discoveries. Snippet commentary separates known fit from missing responsibilities;
employer ruling appears only on roles identified as Dutch. No model assessment was
invented to fill missing coverage, and no live research, retry or API fallback was run.

Final offline verification: **272 Python tests, 266 passed, 1 failure, 5 errors**, no
skips. The remaining legacy catch-up/active-workspace launcher failures are unchanged
from the earlier diagnosis. **14 DOM tests passed**. Chrome verified a synthetic local
24-candidate report, all retained cards, explicit pending/excluded counts, unverified
title salary ceiling and no console warnings/errors. Compilation and whitespace passed.
Private existing-record projection and restart verification kept every stored SQLite
table row unchanged; the same workspace was reopened without a new research run.

## Verification-first bottleneck diagnosis (14 October 2026)

This supersedes the eight-job assessment batching described above. The preserved
local run contains 73 accepted observations: 24 selected and 49 lower relevance.
Eight selected jobs have preliminary assessments, four are source-confirmed closed,
and twelve remain pending. Only one nonclosed job has a stored full description;
the other four full descriptions belong to closed jobs. The remaining 68 jobs are
snippet evidence. An HTTP 200 or indexed tool result alone does not prove complete
responsibilities, requirements, or vacancy availability.

The saved run lasted 595.123 seconds against a 900-second outer limit. Its phase
allocations were discovery 600, enrichment 150 and assessment 150 seconds. Recorded
AI call time was distributed as follows:

| Work | Recorded seconds | Verified implication |
| --- | ---: | --- |
| Four indexed discovery calls | 344.604 | Two additional passes consumed 176.145 seconds, including a 90.193-second failed call |
| Two private relevance triage calls | 42.529 | Country-sized selection batches prevented one global comparison; source work ran between them |
| Three successful assessment calls | 94.277 | Eight preliminary decisions retained |
| One failed assessment call | 53.629 | Five candidates shared one timeout, not five independent CLI failures |

Assessment AI time totals 147.906 seconds, almost the entire 150-second phase.
Seven location-unverified selected jobs were therefore never evaluated. The remaining
elapsed time includes source transport, spacing and coordinator work; diagnostics do
not establish a precise per-request duration, so these are not assigned invented costs.
There is no evidence of lost saved jobs: all 73 records remain. The original completed
phase label and four closed jobs counted as cached assessment overstated completion.

Recorded transport comprised three direct LinkedIn searches, five LinkedIn details
(all HTTP 200), and eight public HTTP requests: four robots requests, two HTTP 200
pages, one 404 and one 410. Of the two public pages, one exact posting was rejected
by the HTML fallback and one was a general careers homepage. The exact page uses an
`article-wrapper`; the parser did not recognize it and could terminate a job region
at self-closing void tags. Offline replay of the saved bytes now recovers 3,314
characters from that exact posting, with zero requests and an unchanged snapshot
hash. The general homepage still fails identity validation. Source access failures
remain unknown/unverified, never evidence that a vacancy closed.

Selection returned AI priority order but the coordinator converted IDs to a set,
then read database order and evaluated verified-country groups before unknown-country
groups. The fix persists shortlist ranks, completes compact triage before source work,
and uses those ranks for both verification and assessment. Observed employer sources
are attempted before consented direct LinkedIn details. Broader discovery is deferred
after one primary indexed pass per selected market. Phase limits were not increased.

Final assessment receives only active verified descriptions, at most two jobs per call
and a bounded batch context. Large individual descriptions remain intact and isolated;
duplicate snippet/CV-derived context is omitted. Less than ten seconds remaining does
not launch another doomed assessment call. Every successful batch survives a later
failure. Strong recommendations require a verified source description and a literal
non-metadata duty/requirement quotation; model reasoning still determines career fit.
Coverage separates preliminary assessments, verified assessments, missing sources and
pending evaluations. No stored historical assessment is rewritten to invent completion.

Verification: **286 Python tests: 280 passed, one failure and five errors**, no skips;
**14 DOM tests passed**. Compilation, JavaScript syntax and whitespace checks passed.
New regressions exercise priority order, compact global triage, complete requirement
tails, small assessment batches, timeout preservation, insufficient source evidence,
exact HTML regions and unchanged identity gates. Tests contain synthetic vacancies;
the existing-record replay remains private. No live AI, publisher research, retry,
API-key fallback or user database update was performed for this implementation.
The six earlier failures remain listed as open tasks below and were neither skipped
nor removed. Offline scheduling improvements do not prove future live source yield.
