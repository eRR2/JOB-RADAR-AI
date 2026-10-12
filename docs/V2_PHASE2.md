# V2 Phase 2: independent markets and feedback UX

Branch: `feat/v2-phase2-market-ux`, based on Phase 1
`d5f1d613650063f3aefbf01003ebdd3410bf5f85`. No merge to main.

## Behavior

Discover and Reports offer Germany, Netherlands, All, and Country unverified.
Preferences can configure one to six countries using a unique country code/name,
locations, languages, regional conditions and regional hard requirements. Defaults
are initial markets, not a restriction to those two countries. Global CV, career
objectives, global preferences and application history remain shared.

Each country has an independent AI plan, learned preferences, assessments,
preference revision and run outcome. Query locations must match a configured
country-qualified location before transport, including exploratory queries.
Natural-language queries still depend on fallible AI reasoning and source search
semantics; a country filter does not prove the returned listing's country.
Only explicit source country fields or complete country tokens establish country.
Cities alone and search provenance never silently establish country. A listing
with an explicitly different configured country cannot be recommended in that market.

Search all is one run with independent country outcomes. Countries split the
existing global query/detail/request caps fairly; remainder allocation rotates
between runs. They share one LinkedIn transport, persistent request spacing,
cache and stop latch. Unused quota is not automatically transferred. Very small
budgets can leave a country without descriptions or requests; outcomes show this
as incomplete. A failed country's results never remove another country's jobs.
All counts deduplicate job identities; separate market assessment counts are retained.

Like/Dislike/Irrelevant default to the listing's stated country, otherwise
unclassified. **Apply to all markets** explicitly selects global scope. Regional
feedback and regional learning edits invalidate only that country's assessments;
global changes can invalidate both. Previously recommended assessments remain
visible with **Reassessment pending** until a validated replacement is saved.
Like is visibly persisted on reopening. Save/application transitions remain
independent and rejection never trains negative preferences.

All seven sliders and their UI implementation/styles are removed. New profiles
need no weights. New assessments have exact evidence and separate ATS/HR reasons,
nullable subjective dimension assessments, and no weighted/composite total.
Historical scores remain labeled **Legacy assessment / Legacy score**. Sorting
puts AI recommendations first, then discovery date; no hidden weighted ranking.

The native opportunity dialog closes on a click outside its bounding rectangle;
inner clicks and padding do not close it. X and native Escape/modal focus remain.
Dialog scrolling is bounded to the viewport. Identical display warnings are
deduplicated; individual source, description and evaluation failures remain in
the private run outcome. Failure/partial outcomes are never displayed as fully
successful.

## Migration and recovery

Schema version 2 adds `job_markets`, `market_evaluations`, `feedback_scopes`.
Version 1 is backed up through SQLite's consistent backup API under
`.private/backups/migration-*.sqlite3` before DDL. Integrity and all seven original
tables are compared; failure refuses migration. Backfill is transactional and
idempotent. No original job, evaluation, feedback, application event, report,
source restriction or CV is deleted/replaced. Original profile keys are retained.

Standalone country geography has a deterministic regional destination. Ambiguous
free-text geography is preserved under `market_migration.legacy_geography` for
review, without guessing a city/language/country. Searches and Run now require
the user to save regional conditions and confirm this review in Preferences;
a refusal does not consume the catch-up slot. Old feedback with an explicit
country is scoped there; otherwise it stays unclassified and excluded from
regional learning. Old learned preferences remain inspectable for scope review.
Resubmit unclassified feedback locally after country evidence is available, or
explicitly globally. No automatic reinterpretation invents a regional preference.

Recovery is an explicit operator action with the workspace closed: preserve the
current database and any records added since migration, restore a verified backup
to a separate private copy, and use the Phase 1 checkout against that copy. Do not
overwrite current history. Synthetic regression tests exercise the backup/down
path and preservation of original rows. No automatic rollback/reset is offered.
App-created migration backups are included in explicit career-data erasure;
operator verification snapshots are retained separately for deliberate recovery.

Catch-up retains Run now / Remind later / Skip, one persistent slot and one All
run with country outcomes. No OS task, hosting, cloud database, new dependency
or manual runtime installation is introduced. MIT/upstream attribution and the
existing Codex/LinkedIn adapters are preserved.

## Verification evidence and limits

87 automated Python tests cover markets, migration, feedback, catch-up and HTTP privacy;
74 upstream offline Bun tests; seven Node DOM/handler tests; JavaScript syntax; staged
privacy scan plus reachable Git history and eight ignore probes. Synthetic DOM
tests are not real-browser, visual, Escape-key or accessibility verification.

Live subscription Codex completed two independent country plans, triage and
validated assessments using an isolated synthetic database/source. Both outcomes
completed, one assessment per market, zero warnings; query locations were
Germany and Netherlands. Four synthetic transport calls, **zero LinkedIn network
requests**. This verifies actual Codex integration, not real regional coverage.

Before the existing private database was migrated, a separate consistent snapshot
and original CV files were verified. After migration all 26 jobs, existing
evaluations, feedback, application events, reports, observations and cache rows
were compared, as were all original profile fields/settings and CV hashes.
Source restrictions were unchanged. Ambiguous regional preferences require review.
No personal payloads or backup contents were printed or committed.

No browser automation surface is connected in this session. The current dashboard
is checked through loopback HTTP; real browser visual/click/accessibility QA and a
clean Windows machine remain unverified. Claude is unchanged/unverified.
Supplementary imports still require complete fetched-page evidence unavailable
from current adapters. `pip check` verifies installed dependency consistency.
Upstream `bun audit` reports **Lockfile not found**: its optional development
dependency advisory audit is unavailable, not a test failure or vulnerability
finding. Runtime Bun code has zero package dependencies; no dependencies changed.
The privacy scanner supplements human source/prose review and cannot prove that
arbitrary prose contains no personal information.

## Try the dashboard

Invoke `$job-radar-ai`, then open Preferences, review preserved geography, set
each country's conditions, and use **Save conditions & confirm my review**.
Discover's Germany/Netherlands tabs use **Search this country**; All uses
**Search all markets**. Reopen a liked job to see persisted Like, and check its
Reassessment pending badge. **Apply to all markets** changes feedback scope.
Reports shows each country's strategy/outcome under one run. Source restrictions
remain in force; do not clear them to bypass denial.
