# JOB-RADAR AI

Independent local career hunter. Read README.md, docs/ARCHITECTURE.md and tasks/todo.md.
AI providers own strategy, content analysis and learning. Python transports, validates,
persists and protects data; never add keyword matching as the intelligence.
Keep all private material under .private/. Synthetic tests only. Preserve MIT attribution.
No Outlook, automatic applications, arbitrary model shell commands or access bypass.
LinkedIn 429/interrupted requests stop only the current search session; each validated manual search clears legacy local cooldown/pending/stop state. Honor explicit unexpired publisher Retry-After, robots, authentication and explicit denials across sessions. Other publishers retain their access policy. Never retry within the same run after denial, bypass restrictions or substitute denied endpoints. Indexed web research is independent of direct LinkedIn transport.
Use `python -m unittest discover -s tests -v`. Test behavior before changing it.
Publishing requires an explicit user request and a staged privacy check.
