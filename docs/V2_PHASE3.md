# V2 Phase 3 — description recovery and safe updates

Base: `fd35a7c9a4d2092bc16e7f973c7109f1f4e1b8e1` (Phase 2.1).
Feature branch: `feat/v2-phase3-recovery-updates`. Preview version: `2.3.0-phase3`.
No main merge, stable tag/publication or change to another user's installation.

## Actual approved source test — 2026-10-12

Developer SQLite was consistently copied into ignored `.private/verification/phase3`.
Ten previously discovered missing-description identities were selected. Existing source
stops were copied and honored; no reset, fresh-DB evasion or duplicate jobs.

| Metric | Actual count |
| --- | ---: |
| Attempted existing vacancies | 10 |
| Recovered full descriptions | 6 |
| Unavailable/unverified/deferred | 2 |
| Access restricted | 2 |
| Existing evidence-backed AI assessments | 6 |
| Remaining missing descriptions | 4 |
| LinkedIn detail requests | 5 |
| Controlled public HTTPS requests, including robots | 8 |
| Cache hits | 0 |

Five descriptions came from the existing LinkedIn detail integration. One came from
real employer JobPosting JSON-LD at `vitestro.com`, independently retrieved with URL,
SHA-256, byte count and timestamp. Six real selected-subscription Codex evaluations
passed the existing exact CV/job quote and country-profile validation. Private source
text and personal AI outputs remain ignored and are not published.

Remaining outcomes: two publisher challenge/access restrictions, one ambiguous/unverified
identity and one deferred public-request budget. No automatic retry or bypass. These
are real source/coverage limitations, not successful empty retrievals. A later operation
may use cached/user-supplied text; blocked vacancies/publishers remain blocked.

Greenhouse, Lever and Ashby were tested with synthetic public-API fixtures only.
Lever/Ashby require a fetched employer Organization plus an exact posting link because
their feeds omit the employer name. This conservative gate may refuse real listings
whose employer page has no usable structured ownership evidence. Exact title/locality
matching also rejects translated/ambiguous equivalents rather than merging wrong jobs.
Generic HTML without JobPosting, scripts requiring browser execution, credentials,
restricted sources and unsupported encodings/providers can remain unverified.

## Preserved boundaries

No schema change: SQLite user_version remains 2. Developer has 26 jobs; every table's
row hashes, schema version and retained CV bytes were compared before/after. Original
ID/URL, feedback and application events are retained in recovered test jobs. No private
records in the developer or second-user workspace were updated. No live LinkedIn search
was performed. Existing Hunter strategy and subscription adapters were reused.

Description status distinguishes never attempted, budget deferred, attempted failure,
access restricted, incomplete description, verified source unavailable, identity unverified,
verified source text and explicitly user-supplied text. Batch work shares the one-run
lock/cancellation gate and is bounded to ten identities. Unknown-country jobs never
receive a guessed country; automatic assessment requires a configured verified country.

Fetcher uses TLS, validated/pinned public DNS addresses, GET only, no proxies/cookies,
bounded child execution/bytes/redirects, robots policies and persistent publisher stops.
No career/CV/profile fields are passed to source websites. AI locator receives public
vacancy facts only. User career context goes only to the consented subscription provider.

## Update experience

[Update instructions](UPDATES.md) describe exact stable Release staging, independently
reviewed SHA-256, full file inventory/hash validation, approved same-workspace replacement,
private/code backup verification, copy-error rollback, journal recovery and relaunch.
Custom Documents paths are supported through registered canonical skill/managed manifest
discovery; no username/LOCALAPPDATA assumption. The first-install helper now refuses
replacement of existing managed code. Provider login/skill association remain in place.
The local release builder prepares assets but does not tag/publish; preview cannot become
a stable asset without a separate reviewed stable-version commit.

## Verification

Windows update smoke test installed the exact older Phase 2.1 public archive into
an isolated custom Documents path, using a synthetic existing profile, CV, report,
Like/Interview history and persisted source stop. Updating while running was refused.
After guarded close, the staged current code replaced the same managed workspace;
the same health/database identity was relaunched and inspected in the actual browser.
All table rows/schema, CV/report bytes, runtime and exact skill binding were preserved.
SQLite's file-header transaction counter and launcher log changed on startup; these
are not user-record changes. Runtime binaries were reused locally, no downloads.
The target revision marker was synthetic; this is not a real stable Release upgrade.

Final suites: **132 Python**, **74 Bun / 136 assertions**, **15 Node**, no skips;
JavaScript syntax and six locked Python dependencies passed. Staged/history privacy
scan passed **90 indexed public files and 8 ignore probes**. No dependencies were added.

Full Python/Bun/Node, syntax/dependencies and staged/history privacy checks are recorded
at final branch verification. Offline regressions cover strong identity rejection,
controlled retrieval despite missing provider page telemetry, DE/NL evaluation isolation,
preserved records, source-stop persistence, SSRF/robots/redirect/size limits, consent/CSRF,
custom-directory updates, archive tampering/private paths, interrupted-copy recovery and
private SQLite/CV preservation. A code-hash guard inversion made the update suite fail;
the original source was restored byte-for-byte and the full suite rerun.

Actual in-app Chromium interactions verified single/batch retrieval, persisted Like/Save,
country assessment labels, recovery report counts and public update check. Test source
retrieval and AI in this UI fixture were synthetic, separate from the approved live source
test above. Console error/warning check was empty. This is not a complete accessibility audit.

The second real Windows installation's success is user-reported. This session uses the
development Windows PC with isolated private workspaces and existing runtimes, not a
clean VM or direct interaction on that other PC. No real stable Release download/update
can be claimed before the first approved Release exists. Live Claude is still unavailable.
