# Shared operating workflow

## Setup

Use the independent MIT repository https://github.com/eRR2/JOB-RADAR-AI. Download and extract a release/ZIP or use an existing checkout; preserve existing directories. On Windows, open `Launch JOB-RADAR.cmd` (first launch runs `setup.cmd`). Python 3.11+, Bun, and a separately installed, subscription-authenticated Codex or Claude Code CLI are prerequisites. The launcher opens the loopback dashboard at `http://127.0.0.1:8767`. Read the README for official prerequisite installation links and limitations. The application never obtains the provider's credentials itself.

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

Reports contains the latest and historical run outcomes, actual source successes/failures, requests, cache hits, new/previously seen jobs, descriptions, evaluations and AI analysis. Distinguish completed, partial, failed, canceled and skipped runs. Never claim execution while the computer is off. Daily/weekly scheduling uses local time while the runtime is active; a native task needs explicit user confirmation and runs only on a powered-on machine with the user logged in.

## Private state

The ignored `.private` folder contains SQLite state, CVs, feedback, reports and backups. Export is private. SQLite backup is consistent; restore only explicitly with the app stopped, retaining the damaged database for diagnosis. No mailbox integration, auto-application, remote backend or paid API is part of this workflow. Provider-owned histories and Windows tasks are managed separately from app data deletion.
