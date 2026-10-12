# Phase 4.1: reliable fallback and concise review

Base: `3343205440cc6e8b85edfd4ecbae195562ca5856`.
Branch: `feat/v2-phase4-1-search-and-ux`; preview, not a stable Release.

## Focused changes

Confirmed AI intent no longer disables independent official-source exploration.
An ATS failure or no candidates can trigger one bounded supplementary research pass,
even if the initial plan did not request it. Country/location context is passed explicitly.
All retrieval shares the existing request and publisher caps. No budget was increased.
A stopped publisher is skipped while another independently published official source
may continue; LinkedIn remains stopped. Exact identity, retrieved text, robots, TLS,
SSRF, byte/time bounds and cancellation remain enforced. The same validated retrieval
boundary handles documented ATS, JobPosting and controlled official HTML sources.

Public HTTP errors now retain their numeric status. Reports include the suggested board,
actual endpoint, allowlisted public query parameters, response status and posting-identity
verification state. They exclude CV/profile context, credentials and raw response bodies.
An empty or failed board is not labeled identity-verified. All-source failures explain
unavailable source coverage rather than claiming there are no relevant jobs.

The SmartRecruiters [documented endpoint](https://developers.smartrecruiters.com/docs/endpoints)
uses the company identifier from its published career-site URL. The earlier two HTTP 400
requests cannot be reconstructed: their board IDs/parameters were not persisted.
This patch fixes diagnostics and recovery from that failure; it does not claim to have
identified or repaired an unknown rejected parameter. SmartRecruiters is live-verified;
the other four adapters retain their experimental labels.

Review now emphasizes one large editable understanding, **Looks right — continue** and
**Edit my preferences**. Original words/CV remain available in a collapsed section.
Individual preferences, provenance, country/scope fields and hard constraints are inside
one collapsed Advanced Preferences section. Source permissions remain separate.
Editing the summary requires reinterpretation and another explicit confirmation; the
server rejects changed-summary acceptance. Original words, legacy profile and history
remain preserved. No mandatory salary, leadership or career defaults were added.

## Lean verification

73 relevant Python tests and 18 Node DOM/handler tests passed; JavaScript syntax and
Git whitespace checks passed. Only two focused source tests and one UI regression were
added; the existing HTTP onboarding test also covers summary reinterpretation.
Offline fixtures prove HTTP 400 status retention and confirmed-intent fallback despite a
LinkedIn stop and another denied publisher, without increasing requests or resetting stops.
No repeated full-suite, dependency installation or broad security campaign was performed.

One consent-approved isolated live trial used a synthetic career profile and a previously
verified BoschGroup board seed. Genuine Codex planning, candidate selection and evaluation
ran with model web tools disabled. SmartRecruiters returned 20 real German cards; two exact
details supplied full verified descriptions and both received validated AI assessments.
Three controlled HTTPS requests, zero LinkedIn requests, preserved copied stop.
The run is honestly `partial` because LinkedIn was skipped. This proves the seeded
source-to-storage-to-AI path, not unconstrained AI board selection or a live cross-provider
fallback; those boundaries have offline coverage. No second live trial was run.

Chrome rejected the separate synthetic onboarding page with `ERR_BLOCKED_BY_CLIENT`.
Actual browser/onboarding interaction remains unverified; HTTP and DOM tests are not
claimed as visual QA. The developer database/CV have a consistent before-backup and
all-table/schema/CV fingerprint checks. Private test evidence is excluded from Git.
Staged files/history privacy scanning is required before publication.
