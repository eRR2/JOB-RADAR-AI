# Phase 4 implementation and verification

Base: `35b4da4aed93f03c1f649d74e39599ca83a34ab0`.
Branch: `feat/v2-phase4-ai-first-multisource`.

Work is isolated from the developer's running Phase 3 dashboard. The private
database is backed up with consistent SQLite backup and table/schema/CV fingerprints.
No second-user installation, main merge or stable Release is in scope.

## Implemented behavior

CV preview and one next-move text replace the long onboarding wizard. Subscription AI
proposes a short editable intent with exact CV evidence and explicit/CV/inferred/unknown
origins. Only explicit, user-confirmed preferences can become hard requirements. At most
two essential questions are allowed; salary/leadership remain optional. Reviewed place
names and city/region/country/mixed scope prevent treating proximity prose as a city.
Review survives reload; a changed next-move text requires reinterpretation, and current
provider/source permissions are validated again at acceptance. Optional detailed settings
are inside Advanced Preferences. No new CV upload or database migration is required.

Original user texts and a full legacy profile snapshot remain in local storage. New
country-specific inference receives only its reviewed intent and global/same-country
preferences, not archived profiles, raw multi-country prose or another country's edits.
The old profile remains usable until the user reviews and explicitly replaces it.

Query scope is checked before transport, with one bounded plan correction. Valid queries
survive correction failure; only explicitly permitted remote queries get a country-level
exception. Actual source location determines preferred/secondary/verified remote/outside/
unknown labels. Unproven regional membership stays unknown; commuting time is never
invented. Clear location conflicts and confirmed hard violations cannot be Recommended.

Independent public ATS discovery uses dynamic employer-board suggestions, fetched vendor
schemas and source evidence. SmartRecruiters can use the confirmed primary city filter;
providers without that filter use a bounded board response and rank actual locations.
Only 20 cards per board are retained in a search sample. One Search all operation shares
up to 8 controlled public requests, capped by the saved request setting, with at most 4
per publisher. Individual/batch recovery shares at most 16 (also capped by saved setting),
4 per publisher and 10 existing identities. HTML robots requests count toward those caps.
Pages cache for 24 hours; LinkedIn retains its separate existing global budget and spacing.

Exact source IDs, canonical links or known requisitions plus employer/title/locality/country
gate cross-source association. Ambiguous recovery keeps fetched candidates for explicit
confirmation. Ambiguous deduplication keeps separate raw records flagged for review.
Original job ID/URL, feedback and application history survive association. Full text at
discovery is prioritized within the existing assessment quota and evaluated under its
verified country. Selected missing descriptions can recover progressively during the same
operation; individual/batch controls remain available without restarting discovery.

Stages are Discovering, Verifying descriptions, AI evaluating and Ready to review.
Reports distinguish actual HTTP denials from persisted shared-stop skips and budget
deferral. Publisher restrictions stay latched. Complete text never means the vacancy
is still OPEN; availability remains unknown without source evidence.

## Provider evidence and references

| Adapter | Public contract | Phase 4 verification |
| --- | --- | --- |
| Greenhouse | [Job Board API](https://docs.greenhouse.io/job-board.html), compact board metadata/list then selected job detail | Offline schema/identity tests; experimental |
| Lever/EU | [Postings API](https://github.com/lever/postings-api), bounded list/detail, fetched employer ownership | Offline schemas/ownership; experimental |
| Ashby | [Public posting API](https://developers.ashbyhq.com/docs/public-job-posting-api), bounded response, listed jobs and employer ownership | Offline schemas/identity; experimental |
| SmartRecruiters | [Posting endpoints](https://developers.smartrecruiters.com/docs/endpoints), 20-card country/city list and exact small detail | Live full descriptions plus real Codex evaluation |
| Workable | [Documented public jobs endpoint](https://help.workable.com/hc/en-us/articles/115012771647-Using-the-Workable-API-to-create-a-careers-page), account jobs with details | Offline schema test; experimental |

The four unproven integrations are visibly experimental, not advertised as live-verified.
Oversized boards are incomplete; no silent truncation, retries or alternate denied routes.
Greenhouse updated timestamps remain updated timestamps, not invented publication dates.
Lever/Ashby ownership requires an actual employer link and Organization evidence; an AI
company/slug assertion alone is insufficient. Controlled official HTML fallback requires
job-specific canonical URL, unique main/article, exact title/employer and identity text.

Reference review: [JobSpy](https://github.com/speedyapply/JobSpy) and
[wickfeed](https://github.com/wickfeed/ats-job-aggregator) are MIT architecture references;
no proxy/stealth or paid Apify dependency was adopted. The
[endpoint catalogue](https://github.com/noble-ronin/ats-job-apis) is a discovery reference,
independently checked against vendor documentation. [Trafilatura](https://github.com/adbar/trafilatura)
is optional Apache-2.0 extraction reference; it was not installed or imported. Existing
LinkedIn attribution and transport are retained; no new runtime dependency was added.

## Isolated live comparison

User-approved ceiling: 20 controlled official ATS HTTPS requests, 8 job AI evaluations,
zero LinkedIn requests, preserved publisher stops, and a private copy of the database.
Actual trial used **5 HTTPS requests and 3 Codex job evaluations**. SmartRecruiters returned
20 German cards; three exact detail identities supplied full descriptions. Real responses
revealed lowercase country filtering and non-text video sections; corrected adapters
reused cached responses without extra source requests. No CV/profile went to publisher APIs.

| Measure | Developer baseline | Private comparison copy |
| --- | ---: | ---: |
| Jobs | 41 | 44 |
| Full descriptions | 15 | 18 |
| Country assessments | 15 | 18 |
| New full descriptions / completed assessments | 0 | 3 / 3 |
| New recommendations | — | 0 |
| Original missing descriptions recovered in this trial | — | 0 |
| False identity associations / merged duplicates | — | 0 / 0 |
| LinkedIn requests / actual HTTP denials / budget deferrals | — | 0 / 0 / 0 |

These are three new postings, not recovery of three original missing records. All three
had source-stated Germany; this trial does not prove preferred-city improvement or positive
career fit. No recommendation success was fabricated. Original 41 job rows were identical
in the copy, and developer table/schema/CV fingerprints stayed unchanged. Original source
stops were retained. Cross-platform deduplication/ambiguity and region rules have synthetic
coverage, not a claimed live cross-platform match.

## Verification and limits

Four synthetic career/geography cases cover senior technical, SAP/process, junior changer
and unspecified salary/leadership. HTTP/DOM tests cover review, provenance, permissions,
CV-change/input-change guards, regional isolation, persisted Like/history, unknown country,
assessment selection, backdrop closing and optional advanced controls. Source regressions
cover SSRF/all-DNS-address checks, pinned TLS, same-host redirects, robots, byte/time/cancel
bounds, malformed schemas, requisition/location conflict, cache/stop/budget distinctions,
exact association and source text only. A publisher-budget guard mutation failed the
pipeline tests; the original file was restored byte-for-byte and tests rerun.

Actual reviewed public code was installed in separate fresh and existing managed Windows
test workspaces. Phase 3 to Phase 4 update preserved private snapshot and skill binding;
relaunch retained CV, Like, interview history and source stop. A fresh Phase 4 launch had
empty profile/CV/jobs. Existing local Python/Bun were reused; no download or second-PC
change. Release metadata/revision were synthetic QA markers, not a published stable Release.

Final regression counts: 159 Python tests, 74 Bun tests (136 assertions), and 17 Node tests,
all passing without skipped tests. JavaScript syntax and Git whitespace checks passed.
Real Codex also interpreted a synthetic junior career-change CV and Toronto/Canada intent
with valid source provenance, zero essential questions, no compulsory salary/leadership
requirements and zero source requests. Staged files and complete Git history are checked
by the privacy scanner before publication. Six locked Python runtime versions matched the active
venv; [OSV batch audit](https://google.github.io/osv.dev/post-v1-querybatch/) returned no known
advisories. Native `bun audit` cannot run without the upstream optional development
lockfile; the Bun integration has zero runtime package dependencies. This audit limitation
is not presented as a passing native audit.

Chrome blocked the local QA page with `ERR_BLOCKED_BY_CLIENT`. Real visual/click/console/
responsive accessibility verification could not be completed; HTTP and pure DOM tests
are not substituted for that evidence. No browser/security setting was weakened. A clean
Windows VM, actual Codex Desktop skill-selector interaction, second-PC update and live
Claude remain unverified. No main merge, stable Release/tag or second-user modification.

LinkedIn stops remain source-specific. Independent official ATS APIs are not routes
to denied LinkedIn endpoints. Publisher restrictions persist across their own routes.
Unproven integrations are experimental; model text never substitutes for retrieval.
