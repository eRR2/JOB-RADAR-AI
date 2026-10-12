# V2 Phase 2.1 release readiness

Base: `d30099a28f22f8b15d430598a5e874301c97c445` on
`feat/v2-phase2-market-ux`. Work is isolated on
`feat/v2-phase2-1-release-readiness`; main is not merged or updated.

## Changes

- Discover/Reports have configured countries and All only. Ambiguous locations remain
  persisted in All jobs with Location unverified, outside verified-country lists.
- Details select the verified country automatically. Only actual multiple assessments
  for an unverified location show a selector. Missing assessments cannot borrow another
  country's or legacy evaluation; reassessment rejects a conflicting verified country.
- Consent-gated private official Codex CLI setup complements existing Python/Bun bootstrap.
  Existing native CLIs are reused; the optional versioned ZIP has a pinned SHA-256.
  CLI browser login and real inference are separate from Desktop sign-in.
- Reviewed public archives install into a new user workspace. Hash-checked upgrades preserve
  private data and refuse running workspaces/modified code. Skill registration uses the
  documented user directory, points to this exact checkout and preserves existing skills.
- [First-time Turkish setup prompt and exact workflow](INSTALL_CODEX_DESKTOP.md).

## Verification

Synthetic tests cover country/assessment labels, retained recommendations/Like and backdrop,
provider setup messages, private-source refusal, fresh installation, private upgrade preservation,
code-change/running-lock/path-escape/new-file-collision refusal, idempotent skill registration
and CLI consent/checksum. A real first-launch regression covers command completion and reuse.
The isolated first start exposed inherited Windows PowerShell pipe handles keeping an agent's
launch call open for the server's lifetime. The fixed launcher spawns the same hidden Python
server with unrelated handles closed; its calling command now completes independently.

Validation on the development Windows x64 PC:

- Full Python unittest discovery: 96 tests, no skips, using the project's explicit `.venv` interpreter.
- Bun: 74 offline tests / 136 assertions; Node: 11 DOM/handler tests; JS syntax passes.
- Python dependencies: project pip check and isolated managed uv pip check pass (six locked packages).
- Indexed public source package installed in a separate ignored test workspace, initially empty:
  no CV, profile, jobs, runs or feedback inherited. Python/Bun bootstrap used previously verified
  local ZIPs, standalone Python and wheel cache with `UV_OFFLINE=1`, avoiding new runtime downloads.
  This verifies private setup/installation, not a fresh PC's entire network bootstrap.
- Separately approved official Codex CLI 0.162.1 archive downloaded and pinned digest verified.
  The installed private executable successfully performed the dashboard's real inference probe
  and synthetic CV interpretation using the current Windows user's existing subscription login.
  No auth files were read/copied by application/setup code, and no new-person login was simulated.
- In-app Chromium browser: actual synthetic DOCX upload, all three onboarding steps, profile review
  acceptance, empty Discover, All/country tabs, unknown-location label, correct NL assessment,
  conditional selector, saved Like/reopen/pending recommendation, Save history, Reports and catch-up
  Remind later checked. No console errors/warnings during those checks. Backdrop behavior is covered
  by DOM/handler regression tests; this is not a complete accessibility audit.
- Repo skill discovered enabled through the pinned CLI's documented app-server `skills/list`.
  User adapter registration was tested in an isolated skills directory without altering real user
  skills. The pinned CLI schema lacks the newer `perCwdExtraUserRoots` test facility; actual user-wide
  Desktop discovery remains unverified. Production registration uses documented files, not that API.
- Existing-user close/upgrade/reopen passed. Every table-row hash, schema and retained CV byte
  hash matched before/after for both the developer and isolated user. Developer schema stays at
  V2 and all 26 jobs/history remain preserved; the isolated user's Like, Save and reminder persist.
- Staged privacy checks cover indexed source, all reachable history and eight ignore probes;
  private test artifacts and the pre-existing untracked image are excluded from publication.

No search-engine or LinkedIn transport rewrite, schema change or live LinkedIn test request.
No Windows task, permanent PATH/registry edit, system installation or main merge.

A clean Windows VM and a second person's actual Codex Desktop/account interaction are not
available. Current-machine isolated setup cannot prove those environments work universally.
Downloads can be denied; native permissions, an own-account CLI browser login, subscription
entitlement and usage availability may block a new user. Failures stay visible without retries
or an API-key fallback. See the installation guide for friendly Codex-operated recovery.
