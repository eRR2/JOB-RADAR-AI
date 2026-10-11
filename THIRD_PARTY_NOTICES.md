# Third-party notices

## LinkedIn guest CLI

The isolated `integrations/linkedin/cli` and `UPSTREAM_SKILL.md` are derived from [MadsLorentzen/ai-job-search](https://github.com/MadsLorentzen/ai-job-search) at commit `a011214d60f943770e33f7d5f070e1a5f91e3822`, specifically `.agents/skills/linkedin-search/`. Copyright Mads Lorentzen; MIT. The complete original license is retained at [integrations/linkedin/LICENSE](integrations/linkedin/LICENSE). Changes enforce single-request access-stop semantics; see that directory's README. The library has no runtime npm dependencies. MIT licensing does not grant authorization to LinkedIn services or waive platform terms.

## Python dependencies

Installed wheels retain their own full license files in the environment. Exact versions are in `requirements.lock.txt`.

| Distribution | License | Upstream |
| --- | --- | --- |
| pypdf | BSD-3-Clause | https://github.com/py-pdf/pypdf |
| jsonschema | MIT | https://github.com/python-jsonschema/jsonschema |
| attrs | MIT | https://github.com/python-attrs/attrs |
| jsonschema-specifications | MIT | https://github.com/python-jsonschema/jsonschema-specifications |
| referencing | MIT | https://github.com/python-jsonschema/referencing |
| rpds-py | MIT | https://github.com/crate-py/rpds |

Codex, Claude Code, Python and Bun are separately installed user-owned tools; they are not bundled or relicensed by this repository. Provider accounts and remote services have their own terms.
