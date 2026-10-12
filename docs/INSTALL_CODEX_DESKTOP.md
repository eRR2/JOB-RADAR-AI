# Windows: second-user setup with Codex Desktop

V2 Phase 2.1 is on `feat/v2-phase2-1-release-readiness`, **not GitHub main**.
Use a separate Windows account/PC and that user's own ChatGPT subscription.
VS Code, Git, manual Python/Bun installation and a Windows installer are not required.
PowerShell and permission for local files, processes, downloads and browser launch are required.
The bootstrap currently supports Windows x64; ARM64 and organizational restrictions can block setup.

## What the user does

1. Open Codex Desktop, sign in with your own account, and start a **local** Codex conversation.
   If the app needs a folder, choose a new empty folder you own. Allow normal permission prompts
   for the chosen local installation; denied permissions cannot be bypassed.
2. Paste this message (the agent runs the commands, not the user):

```text
JOB-RADAR AI'yi bu Windows bilgisayarda benim için kur ve tarayıcıda aç:
https://github.com/eRR2/JOB-RADAR-AI/tree/feat/v2-phase2-1-release-readiness
Bu dalın docs/INSTALL_CODEX_DESKTOP.md yönergesini oku. Yeni uygulama klasörünü
%LOCALAPPDATA%\JOB-RADAR-AI\app altında hazırla ve belgelenmiş kullanıcı
skill klasörüne job-radar-ai kaydı ekle. Mevcut kurulum/veri/skill varsa koru.
Python, Bun veya ayrı Codex CLI gerekiyorsa özel klasör indirmelerini önce
bana açıklayıp onay iste. CLI girişini benim ChatGPT hesabımla tarayıcıda
tamamlamama yardım et; Desktop girişimin CLI için yeterli olduğunu varsayma.
Bana terminal komutu çalıştırma görevi verme. Yeni, boş veritabanı kullan;
başkasının CV, oturum, ilan veya geri bildirimini içe aktarma.
```

3. Approve the explained private downloads if needed. If prompted, complete the **official
   Codex CLI browser sign-in** with your own account. Desktop sign-in is checked separately:
   executable presence, subscription login detection and successful inference are different facts.
4. In the dashboard, upload **your own** text PDF/DOCX, review extracted text, select Codex,
   use **Refresh installed environments → Test inference**, accept processing disclosures,
   build/review your career profile and configure country conditions/frequency.
5. Later, ask Codex **“JOB-RADAR AI panomu aç”** or select the `job-radar-ai` skill
   (some Codex surfaces use `$job-radar-ai`; Desktop skill selectors may use `@`).
   Restart Codex if the newly registered skill does not appear. Run now / Remind later / Skip
   handles missed searches. Close workspace closes the local application; no Windows task is created.

## Agent-operated setup

1. Resolve the public GitHub branch to an exact commit and obtain its **source archive** over
   HTTPS in a separate staging directory, e.g. `%LOCALAPPDATA%\JOB-RADAR-AI\packages\<commit>`.
   Inspect archive paths and the local README, AGENTS, this document, skill and scripts before
   executing any code. Do not evaluate a remote PowerShell script or use application internals.
   This is a local archive workflow; Git is optional. Never copy a developer's working directory.
2. From that clean extracted package run the reviewed local script:
   `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/install-workspace.ps1 -Revision <commit>`.
   The default workspace is the current user's `%LOCALAPPDATA%\JOB-RADAR-AI\app`.
   `-Destination` can select another explicitly chosen private local workspace.
   The script refuses private source paths/formats, overlapping paths and unmanaged existing targets.
   It installs public source files only and records code hashes under ignored `.private/`.
   First database creation happens at application launch, with no profile, CV, jobs or feedback.
3. From the **installed workspace**, run `scripts/register-skill.ps1` through PowerShell.
   It creates an instruction-only adapter in documented `~/.agents/skills/job-radar-ai`, pointing
   to this exact checkout's canonical skill. It is idempotent and never overwrites another skill.
   On collision, use the workspace as a Codex project; its `.agents/skills` adapter is already present.
   There is no config rewrite, undocumented Desktop hook, plugin marketplace or admin installation.
4. Probe `scripts/launch-skill.ps1 -Check`; when missing, explain pinned uv 0.9.5,
   managed Python 3.13.7, locked Python wheels and Bun 1.3.14, destinations and network requirements.
   Ask consent before invoking the launcher with `-ApproveBootstrap`. Cached ZIPs are checked again.
   Python uses uv's checked python-build-standalone distribution, not a python.org installer.
5. Probe `scripts/setup-codex.ps1`. Reuse an existing native CLI if available; do not locate
   undocumented Desktop internals. Exit 2 / `CODEX_DOWNLOAD_APPROVAL_REQUIRED` means explain and
   request **separate approval** for official openai/codex **0.162.1 Windows x64 ZIP**, then pass
   `-ApproveDownload`. Its published SHA-256 is pinned in `runtime-manifest.json` and checked
   before extraction/execution. All adjacent official resources are retained under `.private/runtime/codex`.
   Only the launched server's process PATH is extended; no system PATH, registry or package manager.
6. If subscription login is absent, explain the browser sign-in and invoke the same script with
   `-Login`. It starts the documented `codex login` flow in a hidden process; the user completes
   it in their browser. Re-probe afterward. Never inspect/copy credentials, authenticate with a
   developer account, request a password/token/API key, or infer entitlement from CLI presence.
   API-key authentication is rejected. Authentication and account/usage failures stay visible.
7. Invoke `scripts/launch-skill.ps1` from the installed workspace; it opens the real default
   browser after matching loopback health/workspace identity. If setup occurred after a server
   was already opened, close that idle workspace through its guarded API/UI and relaunch so
   private CLI discovery takes effect. Do not interrupt active AI operations.
   Verify provider status and Test inference. Browser-open requests alone are not visual evidence.

The dashboard can open for onboarding even before provider sign-in; its provider card explains
how to ask Codex for setup. A CLI login/browser action, working Internet, account entitlement,
Windows sandbox permissions and a successful inference may still be necessary. No claim that
Desktop login automatically supplies a working external CLI is made.

## Later upgrades

Close workspace first. Obtain/review the new public source archive in a separate staging folder
and run its `install-workspace.ps1` against the **same** destination. It verifies all prior code
hashes, new-file collisions and database locks before copying code, removes only obsolete managed source files and
preserves `.private` CV, SQLite, feedback, reports, runtime and backups. Modified code, a running
workspace or an unmanaged directory stops the upgrade before copying. Filesystem write failures
can leave an incomplete code upgrade: stop and repair source files; never delete/reset `.private`.
Do not upgrade by replacing the entire application folder or importing someone else's private state.

For existing Git checkouts (including development), use reviewed Git updates without resetting
user changes and keep the same `.private` directory. This phase changes no database schema;
the existing V2 database needs no migration. Do not run the archive installer over a Git checkout.

## Verified boundaries and remaining limits

See [Phase 2.1 verification](V2_PHASE2_1.md). Isolated installation/runtime, onboarding,
persistence, upgrade and CLI tests run on the development Windows PC. A genuinely clean Windows
VM, a second person's real login and Codex Desktop's folder/skill UI remain unverified.
In-app Chromium onboarding and click checks are also recorded; command/HTTP/DOM tests alone
are not visual evidence. No live LinkedIn requests are needed for these checks.

Official OpenAI documentation consulted on 2026-10-12:

- [Desktop and local folders](https://learn.chatgpt.com/docs/app)
- [Local skill discovery and user skills](https://learn.chatgpt.com/docs/build-skills)
- [Codex CLI installation](https://learn.chatgpt.com/docs/codex/cli)
- [CLI login and authentication](https://learn.chatgpt.com/docs/auth)
- [Windows permissions/sandbox](https://learn.chatgpt.com/docs/windows/windows-sandbox)

The official Windows installer uses remote script execution; this project deliberately uses
the versioned official release archive instead. The private download helper is this project's
reviewed packaging code, not an OpenAI Desktop installation hook or an OpenAI endorsement.
