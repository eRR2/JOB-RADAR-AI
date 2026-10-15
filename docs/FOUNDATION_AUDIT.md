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

## Cross-country assessment order correction

Review of `d9d6cfe` found that grouping countries before batching still violated global
priority: DE-1, NL-2, NL-3, DE-4 became DE[1,4], NL[2,3]. Sorting batches by their first
rank did not fix the lower-priority job inside the first batch. Three coordinator
regressions reproduced this ordering, the same leapfrog across verified/inferred
country scopes, and the incorrect retained assessment of DE-4 before an NL timeout.

The coordinator now forms contiguous scope runs from globally ordered ready jobs,
then applies the existing count/context bounds to each run. The example executes
DE[1], NL[2,3], DE[4]. Market profiles, hard requirements, country-specific learning
and feedback remain isolated; inferred and unknown country scopes receive no
country-specific feedback or learning. Successful earlier work survives a later
timeout without assessing a lower-priority country tail. All three new tests fail
before the fix and pass afterward using synthetic retained records and no network.
The six previously recorded catch-up/launcher failures remain open.
Full offline verification ran **289 Python tests: 283 passed, one failure and five
errors**, with no skips. The failing test names and causes are unchanged. Compilation
and whitespace checks passed; no live AI or publisher request was performed.

## Remaining six test failures investigated

All six previous outcomes were reproduced or verified against their execution
conditions, without skipping tests or reducing assertions:

| Previous outcome | Proven cause and resolution |
| --- | --- |
| Four `test_catchup` errors | Fixtures opened the checkout's 5.3 application but expected V2 catch-up. A temporary root with explicit V2 version now exercises the original reminder, persistence, duplicate-action and failed-start assertions. Current-preview tests separately verify catch-up and automatic scheduler are disabled in both normal and skill modes. |
| `test_markets` catch-up error | Production `Hunter.start(market_id='all')` accepts a market, but the mock accepted zero arguments. The mock now accepts, asserts and forwards `all`; both country results still belong to one persistent run, and duplicate execution remains refused. |
| First-launch fixture failure | The actual dashboard held the checkout-wide update lock. After notifying the owner, the idle dashboard was closed through the guarded endpoint. The unchanged launcher test then passed with a temporary empty database, including independent process launch, second-launch workspace reuse and close cleanup. The workspace lock was retained. |

The investigation also exposed a real current-preview entry-point defect: although
the application disabled scheduling, `__main__ --scheduled` could instantiate the
older `ResearchHunter` directly. A synthetic regression failed before correction.
The 5.3 CLI now rejects scheduled execution before process locks, storage recovery,
schedule consumption or provider construction. Manual searches and legacy scheduled
execution retain their existing paths; the legacy cancellation/lock-release test passes.

Full offline validation: **291 Python tests passed, zero failures/errors/skips**;
**14 DOM tests passed**. Compilation and whitespace checks passed. The six earlier
test outcomes are resolved or explained by their verified execution conditions, with
their original coverage retained. No live research, API fallback or user-data mutation
was performed. The user database's complete table-content digest and row counts were
identical before shutdown and after the full suite. The dashboard remains closed.

The remaining execution condition is explicit: this checkout's first-launch fixture
requires its real dashboard to be closed, because the shared update lock intentionally
prevents simultaneous servers against the same code tree even with different databases.
This pass does not establish live provider/source quality or stable-release readiness.

## Individual triage and source-scoped evidence follow-up (15 October 2026)

Retained diagnostics exposed three independent defects. The enrichment contract
returned selected IDs and a shared reason, so it could not preserve an individual
exclusion rationale. The Outlook matcher considered employer text only in subject
and preview; an acknowledgement with the exact title/requisition but employer name
in sender metadata could not match. Existing jobs did not reconsider preimported
evidence after learning their requisition. In addition, original-URL recovery could
accept a redirected same-title posting with a different known requisition.

Current enrichment requests require strict nested per-job decisions while saved
legacy envelopes remain valid. Reasons separate transferable capability, specialist
gaps and missing information. Missing, unsupported or metadata-only quotations cannot
justify low relevance; those records require evidence. The original proposed action
and the evidence gate are retained. One unsupported decision does not discard others.
Legacy exclusions expose the unavailable individual rationale rather than inventing it.

Read-only mail evidence includes only bounded sender display metadata, subject and
preview, never full body or email credentials. Company corroboration and unique exact
identity remain required. Existing-job requisition updates reconsider retained evidence;
explicit manual corrections survive later imports. Applied status changes workflow
eligibility without reclassifying technical fit. Report coverage also separates that
exclusion from a prior low-relevance label.

Publication facts now retain their source URL/channel, quote, provenance, check time
and report time. An unknown screenshot check time stays null. A later access failure
does not erase prior publication evidence. HTTP 404/410 indicates missing-or-moved
address uncertainty; 429 remains an access stop. An actually observed alternative
can be recovered only through the existing policy and identity gates. Same-title
redirects with a different known requisition are rejected; matching requisitions pass.
Source coverage counts full verified text separately from partial evidence.

Real mailbox matching was replayed in a private database copy. Only two explicitly
approved user-record corrections were subsequently applied atomically with a backup;
technical assessments, CV/preferences and unrelated records remained unchanged.
The supplied LinkedIn closure is channel-scoped. The corresponding exact employer
publication remains unverified because its original URL/requisition was not established.
No new AI research run or direct LinkedIn request was started. Targeted read-only web
checks for the requested employer verification did not establish a definitive result;
an independent empty reference lookup was not interpreted as employer closure.

Validation covers the actual coordinator, nested provider schema, missing/title-only
triage evidence, sender corroboration, late identity, manual correction, application
coverage, moved URLs and channel evidence. Tests use synthetic records; real evidence
and authorized-change receipts stay private.
Final offline checks: **304 Python tests and 16 DOM tests passed**, zero skips;
compilation, JavaScript syntax and whitespace checks passed. The dashboard was closed
after prior notice for the unchanged first-launch fixture and remains closed.

## Own-channel closure regression (15 October 2026)

The review predicate previously inspected only the description-source URL and
legacy aggregate flags. A snippet-only vacancy with aggregate availability unknown
therefore ignored explicit closure on its own normalized posting URL. An unknown
alternate-source observation could also bypass the original channel's evidence.
Synthetic regressions reproduced both defects before implementation; the dashboard
projection also returned the stale triage exclusion instead of the closure reason.

Review now checks the verified description publication first, then the vacancy's
own normalized URL, then legacy flags. Explicit open evidence on the verified exact
publication retains precedence over closure on the discovery channel. Unknown access
and unverified alternate text cannot override explicit channel evidence; 404/410/429
alone still do not establish closure. Freshness uses "Source channel confirmed closed"
without implying closure of other publications. Review eligibility, closure reason
and coverage use the same predicate; closed cards remain in All Opportunities.

Read-only inspection of the retained reported closure confirmed that no full
description source exists, aggregate availability is unknown, and source-channel
closure retains user-report provenance and an unknown check time. The corrected
dashboard projection excludes it for closure without rewriting its stored triage
state or inferring employer publication status. User table contents remained unchanged.

Validation: **309 Python tests and 17 offline DOM tests passed**, zero skips.
The unchanged launcher regression ran with the dashboard already closed. Compilation,
JavaScript syntax and whitespace checks passed. No live research or user-record write
was performed; exact employer-publication verification remains open.

## Retained-source recovery diagnosis (15 October 2026)

The latest retained run contains 16 discoveries, 11 selected candidates and one full
description. Seven selected records retain only LinkedIn addresses; four have public
posting addresses. The public requests returned one full publication and three HTTP
404 outcomes. Those three never reached parsing. The recorded 164.162-second run
shows no provider timeout or enrichment-budget exhaustion. Most missing text therefore
comes from absent retained independent sources and missing addresses, not the length
of the 150-second enrichment allowance. Old records do not establish whether an
unassociated official address was never found or was discarded before persistence.

Regression tests exposed independent implementation gaps: a job-specific observed
publication in the ownership field was skipped with its LinkedIn reference; alternate
page-read bodies were not reused; and native pages used only the HTML main-region
fallback, missing existing JobPosting JSON-LD. Stored observations also dropped page
type and mixed the raw body with title/snippet text. Common error labels hid source
selection, access, parsing and exact-identity failures. Contact masking could remove
numeric LinkedIn identities from diagnostic URLs.

The current path preserves safe actually observed references and typed page bodies,
checks original and observed alternate bytes through the same recovery identity gate,
and reuses verified text before new transport. HTML and JobPosting retain all existing
employer/title/requisition/location checks and description bounds. Missing URLs,
unsafe alternatives, homepages, different LinkedIn identities and conflicting
requisitions cannot supply replacement text. Access failures are shared within the
run, while job-specific identity rejection cannot suppress a different candidate's
valid match. Causes and observation times survive replay; original timestamps do not
become new publisher checks. Selected source gaps now keep enrichment partial.

Read-only private replay inspected 11 saved page versions. Eight versions across six
distinct publications yielded verified source descriptions. Two older publications
that the HTML-only route rejected yielded 4,329 and 1,374 characters from their actual
JobPosting fields. The latest run's 3,314-character description was reproduced exactly.
Those older jobs remain separate from the current 16: this work did not manufacture
additional full descriptions for candidates lacking recorded source bytes. A known
different-role link on an old company catalogue was not treated as a moved exact
posting. Unsupported page structure and a short page shell remain unresolved.

All real records, source exports, hashes and the per-candidate stage matrix stay under
`.private/verification`. User database tables remain unchanged. No live AI research,
publisher request, URL invention, retry or application action was performed.

Final offline validation: **319 Python tests and 17 DOM tests passed**, zero skips.
Compilation, JavaScript syntax and whitespace checks passed. The unchanged launcher
test ran with the dashboard already closed. The full user-table digest matched the
initial read-only snapshot after the tests and page replay. Missing exact source URLs,
unproven moves and unsupported saved-page structures remain explicit open work;
synthetic passes do not establish future live source yield.

## Triage-timeout recovery (15 October 2026)

The later live run is explicitly **not an acceptance pass**. It retained 45
discoveries, sent 44 eligible identities in one enrichment call and hit the call's
60.189-second timeout. Only discovery completed; source verification and assessment
never started. The 80-job/40,000-character triage limit measured only compact job
input, ignoring shared private context and the large per-record decision response.
The timeout escaped the triage loop to the coordinator's outer failure handler.
These records prove the stopping mechanism, not the provider's internal latency cause.

Current triage packets contain at most eight jobs, a 40,000-character input estimate
including shared profile, brief, task and wrapper allowance, and a 14,000-character
decision-output estimate. New wire responses have compact field limits; saved legacy
responses retain their validator compatibility. Each triage call has at most 30
seconds and all triage attempts share 60% of the existing enrichment window, leaving
40% for sources. Timeouts and validation failures leave only their own candidates
pending; other packets continue without retry. Provider-wide failures stop further
inference while earlier valid work remains. Extra packet invocation slots compensate
for splitting and are bounded, reported and still subject to existing phase deadlines.

Direct-query tracing showed that comma/conjunction splitting reduced compound
seniority prose to a generic chief-title phrase. Broad technology/data/executive
listings entered through actual direct search observations. Most had previously-seen
identities, which represents rediscovery matching rather than reinserting unrelated
history into the pool. Query construction now keeps whole semicolon-delimited compact
role phrases; it does not classify or exclude vacancies by title. Private triage still
uses the full CV and next-move request, and indexed discovery keeps technical scope
and leadership progression tied to demonstrated capabilities.

Exact application history excluded the known applied requisition from that live
triage call. Its historical requisition survived, but rediscovery had omitted it from
the current payload. Exact-history matching now carries that metadata into future
rediscoveries without changing the independent application decision. Current versus
missing versus source-channel-closed versus timed-out identities were audited
privately; not rediscovered never means closed. The original failed run now projects
per-job triage timeout from saved call identities without rewriting those records.

The empty recommendations view now states that assessment could not finish when
research is incomplete, rather than implying that weak fit was established. Synthetic
regressions cover first and middle packet timeouts, including a clock consuming the
full 30-second allowance, subsequent source/assessment progress, pending failed
identities and retained previous recommendations. The 73-record fixture still retains
all records and requires all triage attempts before sources; its provider now returns
decisions only for identities actually present in each bounded packet. Its declared
ordering, quote checks and country-scope regressions remain enforced.

A separate controlled replay used all 45 retained records in a private database copy.
One packet failed deliberately; two exact historical descriptions reached a stubbed
assessment boundary and the previous valid opportunity remained available. This
generated **zero real career assessments** and is not live acceptance evidence.
No new AI/publisher research or user-table write was performed. The dashboard was
closed after notice for the unchanged launcher regression. The single live acceptance
run remains an explicit next step after this offline correction.

Final verification: **326 Python tests and 18 offline DOM tests passed**, no failures,
errors or skips. The unchanged launcher fixture passed with the dashboard closed.
Compilation, JavaScript syntax and whitespace checks passed. Full logical contents
of every user database table matched the pre-task snapshot after shutdown and replay.

## Small research rounds after 492fb08

The prior coordinator had two scheduling barriers: every market was discovered
before triage, and every triage packet preceded any source work. Its phase entry
also allocated a fresh phase window. Reusing that transition in a round loop would
silently renew the 150-second source/evaluation allowances.

`SessionSearch` now owns one sequential loop. A focused web call has an eight-job
wire limit; each triage packet reaches source verification and at-most-two-job
assessment before the next packet or discovery. Each validated assessment is saved
immediately through the existing independent quotation validator. No second engine,
new framework, occupational classifier, retry or provider fallback was added.
The 492fb08 compact input/output limits and 30-second triage calls remain.

The actual CV and next-career request enter private brief, triage, assessment and
guidance inference. `research_guidance` distills previous observed findings into
anonymous capabilities, specialist gaps, unsuccessful queries, missing sources and
next queries; only that validated result reaches public research. An obvious private
echo is refused in both initial/cached briefs and round guidance; an unsafe initial
brief is neither cached nor forwarded. Source/CV quotations and application history objects are never
copied into the web context. Employer focus comes only from explicit saved priorities,
with country scope retained. Required country visits precede optional expansion;
other explicit employer focuses remain queued even if the first employer is productive.
Diagnostics record requested focuses and unvisited priorities, not fictitious access
or successful company coverage. A private-guidance failure leaves mandatory visits
possible using the existing anonymous brief and distinct employer focus.

One global deadline and cumulative per-phase ledgers retain the original 900-second
total and 600/150/150-second allocations, scaled only by the existing duration input.
Guidance consumes discovery allowance; round transitions cannot refund time. Fair
country shares and reserved discovery invocations prevent optional work from taking
an unvisited country's allocation. A local round-share expiry does not cancel another
country's reserved share. Actual budget exhaustion remains explicit partial work.

The obsolete
`test_global_triage_finishes_before_source_work_and_preserves_ai_order` assertion is
replaced by
`test_first_packet_reaches_sources_before_remaining_triage_and_preserves_ai_order`:
the first source now requires its eight-job packet to be triaged, rather than all 73.
All 73 observations must still be retained and eventually triaged; the declared AI
source order, eight-job bound, strict identity and quotation assertions remain.
The country-order regression still requires DE-1, NL-2, NL-3, DE-4. A timeout of the
middle NL packet now leaves those exact jobs pending while independent DE-4 advances.
Likewise, the 24-job timeout fixture requires 22 valid assessments and exactly two
pending failed identities, rather than treating the timeout as a reason to stop all
remaining assessment calls. No test is skipped and no evidence gate is relaxed.

New observed bytes/normalized source URLs can reopen an exact pending identity when
a later focused round finds its full page. Mere timestamps/tracking changes cannot
retry unchanged work. The saved page still passes the existing identity/parser gate.
Unique candidate/source diagnostics are derived from records, so repeat evidence
review does not inflate counts. Exact application/rejection history and country-scoped
feedback boundaries remain. The final comparison copies saved AI judgments only,
excludes pending/stale/unverified records, and binds each row to its assessment signature.

Observed **synthetic** success trace:

```text
session_brief
research_v5(DE) -> enrichment -> verify_recorded_page -> priority_v52 -> persist_assessment
research_guidance(NL)
research_v5(NL) -> enrichment -> verify_recorded_page -> priority_v52 -> persist_assessment
research_guidance(DE)
research_v5(DE, next employer focus) -> enrichment -> verify_recorded_page -> priority_v52 -> persist_assessment
```

The controlled middle-triage timeout trace retains the first assessment, records the
failed NL packet once, then reaches source verification and durable assessment in
the next DE round. A separate clock fixture consumes exactly 150 evaluation seconds
across three rounds and retains two valid results when the last call times out;
reentering evaluation grants no extra time. Recorded-page recovery completes a prior
snippet's exact identity without inventing another URL.

These fixtures produce **zero real research or career assessments**. Live acceptance,
missing real employer publications and original closed-channel source questions
remain owner-led follow-up work. No user-record migration or repair is part of this change.

The mixed timeout/budget fixture also preserves the exact timed-out identities when
a later call-budget stop occurs; the final stop reason cannot overwrite their cause.

Verification for this change: **340 Python tests and 19 offline DOM tests passed**,
with no failures, errors or skipped tests. The unchanged launcher regression passed
with the dashboard closed. Compilation, JavaScript syntax and diff whitespace checks
passed. All user SQLite tables matched the read-only pre-change logical digest.
The comparison UI has offline DOM coverage; no live browser/visual acceptance or
live research success is claimed.
