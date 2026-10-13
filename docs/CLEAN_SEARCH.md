# Clean-search simplification acceptance

## Persistent knowledge and disposable sessions

The active 5.3 preview uses `SessionSearch`; historical V5 discovery/recovery coordinators
are not the active workflow. A small SQLite session token guards every worker read/write
inside a transaction. A replaced session rejects stale job, run, cache and temporary-state
writes, including a worker returning after reset. A late genuine publisher denial is the
sole safety exception; it may extend a global restriction, never shorten one or import results.

Before reset, SQLite backup passes integrity and table-content equality checks. A concurrent
workspace change causes reset to fail closed. Explicit feedback is detached from deleted jobs
with country, original reasons/note, source title and identity/session provenance. Learned
preferences and original CV/career text remain untouched; no semantic reinterpretation occurs
inside reset. All other SQL research tables/cache and disposable settings are deleted atomically.
LinkedIn local 429 cooldowns and stale pending/stop flags disappear at every manual search.
A new 429 stops LinkedIn for that session, without retry; it cannot block the next manual
search. Explicit unexpired publisher Retry-After and robots/authentication/explicit denials
remain protected, as do other publishers' active restrictions. Late local LinkedIn 429
writes from replaced workers are refused.

First activation clears pre-simplification results after backup. Restart preserves the current
session boundary and cannot resurrect deleted historical results. Each subsequent user search
backs up and replaces the complete session, including job-specific Applied/Rejected/Obsolete.

## Research and recommendations

### Discovery-first engine

One anonymous background is reused while the CV/goals/preferences/learning signature is
unchanged. One private multi-market strategy supplies role families and source queries.
Selected markets are forwarded to the worker and researched in round-robin order before
any enrichment or assessment. Consented direct LinkedIn search uses the existing budgeted
transport; indexed LinkedIn discovery is separately reported. A 429 stops direct requests
for this session, without blocking independent employer/indexed discovery or bypassing denial.

The bounded total is 900 seconds: strategy 120, discovery 480, enrichment 150, evaluation 150.
Unused earlier time is not needed to unlock later phases; each phase has a reserved allocation.
Private calls remain at most 60 seconds and web calls 90; no timed-out call is retried.
Each market gets one indexed discovery call and up to two productive follow-ups. There is no
total vacancy quota. Source budgets remain enforced. Enrichment selection batches contain up
to 40 actual candidates; only selected candidates incur new description requests. Suitability
evaluation runs after discovery, in country-isolated batches of 20, rotating through scopes.
Calls: 0/1 anonymous brief + 1 strategy + 1–3 web calls per selected market + ceil(N/40)
enrichment selections + sum(ceil(scope_jobs/20)) assessment calls, bounded by phase time and
a hard ceiling of 28 invocations. Unfinished candidates remain honestly unassessed.

Canonical LinkedIn job IDs and transport-noise normalization deduplicate observed URL
variants without merging requisition identities. Missing country/description stays unverified,
not discarded. Discard reasons, per-phase/source outcomes, actual queries, request counts,
AI call duration/timeouts and provider-reported token counts live in the existing Run payload.
The collapsible Research Diagnostics view exposes those records without new AI calls, prompts
or CV text. Timeout tool observations with exact LinkedIn identities can still be retained;
other already saved findings always survive. Broad real research quality is still subject to
one explicitly authorized live acceptance search; offline tests are not evidence of that quality.

Changed career input uses the existing strict geographic-provenance interpreter with at most
one evidence-only correction; unchanged validated intent requires no new interpretation call.
An anonymous professional background is durable extracted user knowledge, keyed to current
CV/goals/learning. It is not a carried-over search plan or results cache. Web calls receive
anonymous background and public geography only. Private batch assessment receives actual CV,
original request and the appropriate explicit/learned feedback scope.

Research saves genuine tool observations immediately. Titles do not determine suitability:
the model must establish actual responsibilities, demonstrated capabilities, credible next-step
ownership/seniority and material gaps. Strong recommendations require literal CV/source support;
critical gaps and known closed/outside-preference jobs cannot be promoted. Source completeness
is independent of suitability. There is no deterministic profession/company classifier.

Actual returned job-specific HTML can be validated and parsed without another source request.
Observed partial text and snippets retain provenance but are never relabeled as full text.
Controlled original-source retrieval respects robots/access rules and exact posting identity.
No per-vacancy AI description resolver or full ATS/HR generation runs in this workflow.

Provider limits: 60s private calls, 90s web calls, 900s phase-aware outer window; no automatic retries.
Identical observations are deduplicated and unchanged assessments reused only inside this
session. Research is instructed not to repeat earlier queries; successive low-novelty batches
without worthwhile new avenues stop. No arbitrary total vacancy ceiling was introduced.
Reported tokens, when available, come from structured provider events; no savings percentage.

## Original simplification evidence

- 10 session/engine tests: real SQL reset, verified backup/fail-closed behavior, detached feedback,
  active/expired restrictions, stale writes and late real denials, blocked-worker return,
  restart isolation, cautious preliminary decisions and native source reuse.
- 6 local HTTP tests: fresh-session boundary before worker start, unchanged intent without an
  AI invocation, removed controls refused, cross-origin/CSRF and private-file safeguards.
- 5 Node DOM tests: exactly two result tabs, honest confidence/freshness, useful preliminary
  ranking versus specialist mismatch, original text/edit preservation and actionable failures.
- JavaScript syntax checked; no live AI research or employer/ATS/LinkedIn requests.
- Real database COPY: 59 jobs and 4 old runs removed; current jobs/runs zero after reopening;
  exact CV/profile/learned values survived. The developer database is backed up separately
  before activation. Original V5.2 staged/unstaged patches are retained privately.

Mocks verify orchestration and strict acceptance contracts, not real model judgment quality.
Live Codex latency/quality, token savings and real vacancy yield remain unverified.
Full accessibility and responsive coverage remain unverified. Earlier V5.2 240s timeouts are not claimed
as solved by measured live evidence. A future short real smoke needs user approval.

No main merge, Release, second-PC modification or new runtime dependency.

## Original simplification activation and browser check

The same developer workspace was launched in skill mode at 127.0.0.1:8767. A new
verified private pre-search backup retained all 59 historical jobs and four runs;
active jobs/runs are now zero. Exact original profile, CV text/filename and existing
learned settings matched the pre-change snapshot after activation. No AI search ran.
Real Chrome inspection confirmed exactly two result tabs, a visible saved CV preview
and nonempty original goals. Tab navigation and reload worked; no console errors were
observed. The initial empty-results screen was visually inspected. This is not visual
coverage of live job cards, model execution or full accessibility.

A focused provider-event fixture also verified actual usage fields, without inventing
cost/token values. Current total: 17 focused Python checks and 5 Node checks, plus JS syntax.

## Search-start hotfix

Both UI search routes now share the career-search workflow. Unchanged confirmed goals
reuse the exact saved countries/locations/conditions without intent inference or revalidation,
even when the uploaded CV differs from the old profile copy. Whitespace-only goal formatting
retains the original text. Changed input is strictly validated before one session reset;
failed interpretation leaves the previous profile and session intact. Quote validation permits
line wrapping and wider source passages while refusing foreign/invented locations or paraphrase.
Validation errors show their actual category without unrelated login/subscription advice.

A verified private database backup preceded the explicitly requested one-time local LinkedIn
429 maintenance. No legacy LinkedIn blocking keys were present in the actual database at that
point; unrelated settings/data were unchanged. The subsequent session-only policy supersedes
that maintenance: local LinkedIn 429 stops are now discarded by every validated manual search,
while an explicit unexpired publisher Retry-After survives. No new migration was added.

Focused hotfix verification: 25 Python checks, 6 Node checks and JS syntax passed. Both routes
were also exercised against a private copy of the actual saved CV/preferences, with a mocked
worker: one reset each, zero intent AI invocations, unchanged country/condition records.
No live Codex inference or LinkedIn/source request was made; real research remains unverified.
