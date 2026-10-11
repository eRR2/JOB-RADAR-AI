# Shared operating workflow

## Setup

Use the independent MIT repository https://github.com/eRR2/JOB-RADAR-AI. Preserve existing directories. In V2 the skill executes `scripts/launch-skill.ps1` and opens `http://127.0.0.1:8767` automatically. Follow [the launch boundary](launch.md): missing runtimes require explicit private-bootstrap approval, and a separately installed subscription-authenticated provider CLI is still necessary. The original CMD/setup launchers remain available for V1 recovery. The application never obtains provider credentials itself.

## Career profile

Use Preferences/onboarding: upload a readable text PDF or DOCX, enter objectives and career/location/working preferences, adjust seven weights, and put non-negotiable requirements on separate lines. Let the selected AI propose an evidence-based profile; the user reviews and edits the summary before acceptance. Ask only the proposed necessary follow-up questions. Keep unknown facts unknown. CV contact redaction is best effort; show the extracted-text preview and cloud-processing disclosure.

## Dynamic discovery

Use Search with AI after consent. The AI receives the accepted profile and explicit feedback, generates queries and exploratory role families, and chooses which verified identities merit full descriptions. The attributed Bun tool supplies LinkedIn search/detail transport; the backend only enforces contracts, deduplication, caches, budgets and safety. Expansion is bounded and new candidates receive a second selection pass. Supplementary research uses only real provider web tools and imports only descriptions whose complete source text is visible in tool telemetry. When that capability is absent, preserve the limitation instead of inventing records.

## ATS and HR

Require a retrieved full description and verified identity. Review exact job/CV evidence, domain and actual responsibilities. ATS readiness is a qualitative CV assessment, never an employer's proprietary score. HR assessment separately considers seniority, leadership, transferable experience, gaps and interview risk. Do not add qualifications to the CV. Unknown salary/arrangements are unscored and shown for verification; confirmed user hard-constraint violations prevent recommendation. All Jobs retains the vacancy. Profile/feedback changes mark older assessments stale; use Reassess with AI for a stored description without another source request.

## Preference learning

Use explicit like/dislike/irrelevant reasons and notes. The next search derives inspectable preferences with cited feedback IDs. One vacancy's dislikes remain tentative; repeated confidence needs evidence from distinct vacancies. User edits are preserved. Preferences supports editing, pausing and resetting learning. Application outcomes, including employer rejection, never train negative preferences.

## Applications and reports

Save, Applied, Interview, Offer, Rejected and Dismissed update the intended identity and append dated events. Saved/Ongoing/History are independent of career feedback and vacancy availability. Rediscovery preserves history and does not present an applied/rejected identity as a new recommendation.

Reports contains the latest and historical run outcomes, actual source successes/failures, requests, cache hits, new/previously seen jobs, descriptions, evaluations and AI analysis. Distinguish completed, partial, failed, canceled and skipped runs. In V2 skill mode daily/weekly frequency offers the latest missed slot on opening: Run now starts one bounded run, Remind later defers one hour, Skip persists a skipped outcome. No unattended search, native task or backlog replay. V1's legacy scheduling is only available through its original launcher.

## Private state

The ignored `.private` folder contains SQLite state, CVs, feedback, reports and backups. Export is private. SQLite backup is consistent; restore only explicitly with the app stopped, retaining the damaged database for diagnosis. No mailbox integration, auto-application, remote backend or paid API is part of this workflow. Provider-owned histories and Windows tasks are managed separately from app data deletion.
