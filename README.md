# JOB-RADAR AI

Your own AI subscription, a local career workspace, and opportunities judged by their actual responsibilities.

JOB-RADAR AI is a single-user Windows-first browser application. Codex or Claude Code interprets your CV, creates search queries and exploratory role families, selects descriptions to investigate, assesses ATS/CV readiness and hiring-manager fit, learns from explicit feedback, and writes career reports. SQLite preserves your discoveries and application history. There is no hosted AI service or additional API-key billing fallback.

## V2 skill launch — Phase 1 feature branch

In this checkout, invoke **`$job-radar-ai`** in Codex. The skill runs the fixed local
launcher and opens your real default browser automatically. Upload your CV and
set career priorities, location and daily/weekly/manual frequency in onboarding.
Your profile, actual search results, AI reasoning and feedback persist under
ignored `.private/`; future AI runs read the same SQLite records.

Missing Python/Bun runtimes trigger an approval request for private automatic
bootstrap. You do not manually install them; they remain runtime dependencies.
An installed, subscription-authenticated **Codex CLI** is required for dashboard
inference. Codex desktop/IDE installation alone does not prove CLI availability.
Claude Code's `/job-radar-ai` boundary is prepared but not live-verified here.

Skill mode offers **Run now / Remind later / Skip** for a missed search. It creates
no OS scheduler and does not search automatically while closed. **Close workspace**
stops the server; invoking the skill reopens the same private history. The calling
chat and dashboard inference are separate supported CLI sessions.

See [Phase 2 markets, migration and verification](docs/V2_PHASE2.md) and
[Phase 1 architecture and bootstrap limits](docs/V2_PHASE1.md). V2 is an
unreleased feature branch: copying a standalone skill folder still requires
the application checkout. Clean-machine universal zero-install support is not
claimed. The original V1 entrypoints below and Git history remain recoverable.

## V1 installation — Windows

1. Install **Python 3.11+** from [python.org](https://www.python.org/downloads/windows/) with **Add Python to PATH**, and **Bun** following its [official Windows instructions](https://bun.sh/docs/installation).
2. Install and sign in to **one** supported subscription environment: [Codex CLI](https://developers.openai.com/codex/cli/) with ChatGPT login, or [Claude Code](https://code.claude.com/docs/en/setup) with Claude subscription login. Provider installation/login is separate; this app does not collect credentials. CLI availability and account permissions vary.
3. On [GitHub](https://github.com/eRR2/JOB-RADAR-AI), choose **Code → Download ZIP**, extract into a **new** directory, and double-click **`Launch JOB-RADAR.cmd`**. First launch installs pinned application dependencies into `.venv`; it then opens your default browser at **http://127.0.0.1:8767**. Keep the launcher window open while using the app. Close it to stop the server.
4. Upload a text PDF or DOCX, enter your career objectives/preferences, choose the AI provider, review the privacy and LinkedIn disclosures, and select **Build my career profile**. Review the AI proposal and necessary follow-up questions before accepting it. Use **Search with AI** to start discovery.

Existing provider installations are detected without reading their credential files. Use **Preferences → Refresh installed environments → Test inference** to distinguish installed CLI, detected subscription login, and a successfully executed inference. Claude supports the documented `claude.ai` subscription auth mode; API keys, token-based/unknown modes, Console and third-party billing are refused.

You do not need Git, JSON editing, Docker, LinkedIn login, Outlook, job alerts or prompt engineering. Missing prerequisites are shown as unavailable, never connected. The launcher does not silently install Bun or provider CLIs. `setup.cmd` can be run separately; rerun it after upgrading application dependencies. Future macOS/Linux users can try `sh launch.sh`; those platforms are not live-verified for V1.

## Your workspace

| Screen | What you can do |
| --- | --- |
| Discover | Germany / Netherlands / All / Country unverified; search countries independently, switch Recommended / All jobs / New discoveries, inspect evidence, separate ATS/HR, feedback and reassessment. |
| Applications | Saved / Ongoing / History; change Save, Applied, Interview, Offer, Rejected or Dismissed status with dated event history. Rediscovery keeps the same identity and history. |
| Reports | Independent market strategies/outcomes, discovered/new/seen counts, descriptions, evaluations, recommendations, pending reassessment and source limitations under one run. |
| Preferences | Edit natural-language global objectives/preferences and regional conditions/languages/locations, add countries, review legacy geography and scoped learning, set frequency, review source stops, export/backup/delete private data. |

No demo vacancies appear in the production dashboard. Every observed job remains in **All jobs**, even when low-ranked or missing a description. Applied/rejected/dismissed identities are excluded from recommendations without suppressing the employer or industry. Application outcomes are independent of feedback and never train negative preferences.

There are no preference sliders or mandatory weights. AI interprets natural-language objectives, conditions, CV evidence and scoped feedback. New assessments have no weighted total; historical scores remain labeled legacy. Unknown facts require verification, not automatic rejection. Each hard requirement is assessed unchanged; a quoted confirmed violation prevents recommendation. Previously recommended jobs remain visible as **Reassessment pending** until a validated replacement. Like teaches AI and Save tracks an application independently. Regional feedback affects its country; **Apply to all markets** explicitly makes it global.

CV parsing supports unencrypted text PDFs up to 50 pages or DOCX, up to 10 MB. Scanned PDFs require separate OCR. Extracted text is previewed; common email addresses, phone numbers and URLs are removed, but names and other personal details may remain. AI interpretation and CV suggestions can be wrong: inspect the quotes, actual responsibilities, missing facts and proposed edits.

## Sources and limits

LinkedIn transport is the actual [MadsLorentzen/ai-job-search LinkedIn skill](https://github.com/MadsLorentzen/ai-job-search/tree/a011214d60f943770e33f7d5f070e1a5f91e3822/.agents/skills/linkedin-search), pinned to `a011214d60f943770e33f7d5f070e1a5f91e3822`. Original MIT attribution, CLI and tests are retained; see [integration notes](integrations/linkedin/README.md) for the isolated safety patch.

Guest endpoints are unsupported and automated use can conflict with LinkedIn terms. No credentials/cookies, login, proxies, stealth or bypass are used. Coverage is limited; an observed listing or absence of a closed banner **does not prove OPEN**. Missing search results and source failure do not close a vacancy.

Defaults are 3 dynamically chosen searches, one page per query, 5 selected descriptions, and at most 8 network requests with at least 5 seconds spacing persisted across runs. Preferences exposes bounded changes. Successful searches cache for 2 hours, descriptions for 24 hours; cache reads do not extend freshness. No automatic retries are made. Restrictions, CAPTCHA/auth walls, redirects and unknown request extent after timeout/interruption persist a stop. Review the source stop explicitly; resetting it is not permission to bypass or retry access denial. Search all splits these caps fairly between countries using one shared transport; it never multiplies the global LinkedIn request budget.

Supplementary official-careers/ATS research is optional and uses the chosen provider's real web tools. **V1 currently cannot verify full fetched-page text through the adapters' available CLI output.** Codex can expose actual web actions/URLs, while Claude's JSON result lacks a full tool trace. These are insufficient to validate an entire description, so supplementary vacancies are **not imported** and a visible limitation is reported when research runs. Search/model prose never proves retrieval. LinkedIn full-description analysis works independently. No custom secondary scraper or paid search API is introduced.

## V1 scheduling (legacy launcher only)

Manual, daily and weekly searches are configured in Preferences using the computer's current local timezone. The local server checks due searches while running; the browser tab can be closed. Once-per-local-day attempts and process/database locks prevent overlaps. Failed, partial, canceled, completed and skipped runs persist; interrupted runs recover as failed without pretending completion.

**Create Windows scheduled task** requires an explicit confirmation in the dashboard. It creates a limited-privilege task named `JOB-RADAR-AI`; existing tasks are never overwritten. It uses the fixed local runner, only works while the computer is powered on and the user is logged in, and cannot execute while the machine is off. No OS task was created during V1 verification. Later schedule edits require updating/removing the existing task through Windows Task Scheduler; the app does not silently overwrite it. Provider authentication/runtime access must be available to that same account.

## Privacy and security

- Everything owned by the app is stored below ignored **`.private/`**: SQLite, CV, profile, feedback, source cache, runs/reports and backups. The application does not send these to GitHub and logs no HTTP payloads. The default database is `.private/state.sqlite3`; isolated verification uses a separate database.
- Necessary CV/career context and explicit feedback go to the **selected cloud AI provider after your consent**. Provider terms, retention and account-level history controls still apply; local storage and ephemeral CLI sessions do not guarantee zero provider retention. Public supplementary research receives only search strategy terms, not the CV or feedback.
- No passwords, browser cookies, AI session tokens or LinkedIn credentials are collected. Provider authentication remains in its own CLI. API-key fallback is disabled, and inherited provider key variables are removed for inference.
- The HTTP server binds to **127.0.0.1 only**, with exact Host/Origin checks, CSRF-protected writes, CSP, safe text-only DOM rendering, fixed asset routes, validated uploads and no shell interpolation. CLI calls use bounded argv/stdin processes, restricted tools and strict JSON contracts; retrieved IDs and evidence quotes are validated against actual supplied content.
- CV/job/AI text is untrusted. AI reasoning may still misinterpret facts; quote checking is not proof that every conclusion is correct. The app never applies, sends/replies to messages, accesses Outlook, changes hard requirements or executes vacancy instructions. It is not a security boundary against malware or another program already running as your Windows user. Private files are not encrypted by the app.
- Data deletion requires confirmation and removes app database contents, retained CV and app-created backups. Provider-owned histories and Windows tasks are managed separately. JSON export includes private text and should be protected.

Use **Create local SQLite backup** for a consistent database copy under `.private/backups`. It includes extracted CV text/state, not the original CV binary. To restore, stop the app, preserve the existing `.private/state.sqlite3`, then copy the chosen backup to that exact path before restarting. An unreadable established database fails closed; it is never replaced by an empty one. Keep completed backup copies elsewhere if desired; do not synchronize a live SQLite file across concurrent processes. File deletion cannot guarantee forensic erasure on SSDs/backups.

## Agent skills

The canonical portable package is [skills/job-radar-ai](skills/job-radar-ai/SKILL.md), with one shared workflow reference. Thin repository adapters live at `.agents/skills/job-radar-ai` for Codex and `.claude/skills/job-radar-ai` for Claude Code. Open a session in this repository and invoke **`$job-radar-ai`** in Codex or **`/job-radar-ai`** in Claude Code.

For personal skill installation outside the checkout, copy **the entire canonical `skills/job-radar-ai` folder**, including references, into your platform's personal skills directory (`~/.agents/skills` for Codex; `~/.claude/skills` for Claude Code). Preserve an existing same-name skill and use the platform's documented [Codex](https://developers.openai.com/codex/skills/) / [Claude](https://code.claude.com/docs/en/skills) installation conventions. The application checkout and prerequisites are still needed. Do not copy only a thin repository adapter: its relative link relies on this checkout.

Codex repository discovery was actually verified with `skills/list` (enabled). Both adapter frontmatters and shared-package links were validated; Claude discovery/inference could not be live-tested because Claude Code is absent on the verification machine. Existing unrelated personal skills were not modified.

## Development and verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --check web/app.js
bun test integrations/linkedin/cli/tests
python scripts/check_privacy.py
```

Ensure Bun is on PATH for upstream subprocess tests. See [architecture](docs/ARCHITECTURE.md), [verification evidence](docs/VERIFICATION.md) and [task status](tasks/todo.md). Python stdlib HTTP/SQLite plus native HTML/CSS/JS avoid a server framework and frontend build system; `pypdf` and `jsonschema` are the two direct Python dependencies. Exact runtime pins are in `requirements.lock.txt`. No frontend/npm runtime dependencies are required.

This is an independent project, not a migration of the older JOB-RADAR repository. MIT licensed; [third-party notices](THIRD_PARTY_NOTICES.md) retain upstream rights.
