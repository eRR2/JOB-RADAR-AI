# Isolated LinkedIn integration

Vendored from [MadsLorentzen/ai-job-search](https://github.com/MadsLorentzen/ai-job-search/tree/a011214d60f943770e33f7d5f070e1a5f91e3822/.agents/skills/linkedin-search)
at verified commit `a011214d60f943770e33f7d5f070e1a5f91e3822`.
Original MIT [LICENSE](LICENSE), CLI, tests and skill retained. No runtime dependencies.

Local patch: `htmlFetch` makes exactly one request, rejects redirects, 401/403/429/999,
CAPTCHA/auth walls and unrecognized HTML; no backoff/retry. Search 404 is an error,
not a valid empty result. Matching retry/404 tests describe this new safety contract.
Description whitespace retains upstream parsing behavior. `isActive=true` is never
exposed as verified OPEN. Upstream parsing and command interfaces remain in place.

Guest endpoints are unsupported. Automated use can conflict with LinkedIn terms.
Personal, low-volume operation only; no coverage or availability guarantee. No login,
cookies, proxy, stealth or bypass. Default budgets: 3 searches, one page, 5 details,
8 requests with at least 5 seconds spacing. UI allows smaller bounded values.
Successful search cache: 2 hours; detail cache: 24 hours. Stops survive restarts.
Timeout/interruption also stops requests because actual request extent is unknown.
Reset requires a user-confirmed review in Preferences; do not retry access denial.

To update, obtain an upstream commit, review skill/source/license changes, replace
only this directory, reapply the documented safety patch and run all offline tests.
