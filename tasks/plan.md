# V1 implementation plan

User request supplies the product specification and authorization to build, commit,
create a new public repository and push after privacy review. Existing JOB-RADAR is
read-only reference. OS scheduled tasks remain a separate user-confirmed action.

Stack: Python 3.11+, SQLite, standard-library loopback HTTP server, native browser
HTML/CSS/JS. Two small Python dependencies: pypdf (PDF extraction), jsonschema
(untrusted structured output). DOCX text uses bounded ZIP/XML parsing. No frontend
build, hosted service or API key fallback. Bun executes an isolated upstream CLI.

1. Profile + durable state: normalized weights, independent feedback/application
   histories, corrupt DB refusal. Verify with unittest and process restart.
2. Provider contracts: restricted noninteractive Codex/Claude, bounded/cancelable
   processes, actual auth state. Verify synthetic structured calls and missing tools.
3. Source + hunter: AI plan, searches, AI detail selection, evidence evaluations,
   cautious learning and reports. Verify mocked failures and small bounded live run.
4. UI: real onboarding and Discover/Applications/Reports/Preferences. Verify real
   localhost browser interactions, persistence, cross-site refusal and escaping.
5. Scheduling + packaging: in-process local due checks and optional Windows task
   installation only on explicit UI confirmation; shared agent skill. Verify due
   calculations, supported discovery conventions and setup/launch scripts.
6. Review + release: tests, upstream tests, privacy audit, repository existence/auth
   check, commit/push or exact publication blocker. Verify original repo unchanged.

Risks: subscription/tool availability is account-specific; CLI feature flags drift;
guest HTML may change or restrict access; scanned PDFs require OCR outside V1.
UI reports failure/partial/unknown explicitly. No posting is inferred OPEN.

Trust boundaries: browser -> localhost (exact Host/Origin + CSRF); uploads -> parser
(size/type/ZIP limits); AI -> strict schemas and identity/evidence validation;
source -> escaped text; subprocess -> argv only, no shell and no AI exec tools.
