---
name: /publish-release
id: publish-release
category: Release
description: Publish this project release in one command (GitFlow + tag + GitHub Release)
---

Publish this repository with the project release flow.

Usage:

```text
/publish-release <feature> <release> <version>
```

Example:

```text
/publish-release aief-single-directory-release v0.1.1 v0.1.1
```

Execution steps:

1. Validate input has exactly three values: `feature`, `release`, `version`
2. Run:

```bash
python3 tools/run_github_publish.py --feature "<feature>" --release "<release>" --version "<version>"
```

3. Return release URL from command output

Guardrails:
- Do not skip checks unless user explicitly asks (`--skip-check`)
- Do not force push main
- If publish fails with transient GitHub 5xx, retry up to 3 times before failing
