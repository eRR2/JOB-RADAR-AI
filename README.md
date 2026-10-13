# JOB-RADAR AI — clean search

CV + your original career goals → Search with AI → LinkedIn-first research →
Recommended / All Opportunities. A private Windows browser application using your
own separately authenticated Codex or Claude Code subscription CLI. No API-key
fallback, hosted database, automatic applications or system-wide runtime installation.

Development branch: [codex/clean-search-simplification](https://github.com/eRR2/JOB-RADAR-AI/tree/codex/clean-search-simplification).
Main remains V1; this preview is not a stable Release. The second-PC installation is unchanged.

## Use

Invoke the bundled `$job-radar-ai` skill in a reviewed local checkout. Codex launches
the same private loopback dashboard; no VS Code or manual CMD/Python command is needed.
Missing pinned private runtime or CLI downloads still require your approval.
Desktop sign-in does not prove the separate CLI is authenticated or inference works.
See [installation](docs/INSTALL_CODEX_DESKTOP.md).

Upload a text PDF/DOCX CV and describe your next move in one text field, including
geographic and employment preferences. Search with AI interprets changed input internally;
there is no understanding-approval screen. Unchanged confirmed intent is reused.

Every new search creates a verified local backup, then clears previous jobs, descriptions,
assessments, queries, queues, caches, reports, run histories and job-specific application
states. Only CV/background, original career text, preferences, learned knowledge and relevant
explicit feedback survive. Genuine active publisher restrictions remain separate and protected.
Old workers cannot write into the replacement session. Existing pre-simplification results
are cleared once when this preview is first opened; they remain in the verified private backup.

Recommended presents strong AI-supported next-step decisions first. Title similarity and
transferable skills alone do not establish suitability. Critical specialist gaps remain
explicit; weak roles are not promoted to fill the view. Full and preliminary source evidence
are visibly distinct. All Opportunities contains every genuine discovery in the current
session. Availability remains **Güncellik doğrulanmadı** without positive publisher evidence.

Real native source text is reused locally. Exact matching guards against attaching a different
posting's description. Missing full descriptions do not automatically exclude strong candidates.
No individual AI description-locating loop, separate ATS report, application tracker,
Obsolete control, Promising tab, automatic schedule or technical search-control panel.

## Execution and verification

Research uses an anonymous background; raw CV and private feedback enter private inference
only. Current-session duplicate/query context and cached source failures prevent repeat work.
Changed evidence may be reassessed; unchanged evidence is assessed once. Private calls are
bounded to 60 seconds, web research to 90 seconds, with a five-minute outer safety window.
No automatic retry or provider fallback. Research stops when useful avenues or novelty run out;
response batch size is not a total job limit. Source restrictions and robots rules are respected.

Focused offline checks:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -p test_clean_search.py -v
.venv\Scripts\python.exe -m unittest discover -s tests -p test_clean_http.py -v
node --test tests/web_clean.test.cjs
node --check web/app.js
.venv\Scripts\python.exe scripts/check_privacy.py
```

Historical tests/modules remain as references for earlier branch behavior. Current UI
acceptance is `web_clean.test.cjs`, replacing the earlier multi-tab UI expectations.
No hundreds-of-tests campaign or live subscription research was used for this simplification.
Measured behavior, preserved data and limitations: [clean-search acceptance](docs/CLEAN_SEARCH.md).

## License and privacy

MIT. Attributed LinkedIn integration remains available in the repository; no
`linkedin-jobs-api` dependency was added. CV, database, reports, verification copies,
backups, runtime and provider session files stay outside Git under `.private/` or
existing user-owned CLI storage. Source pages receive no CV or profile content.
