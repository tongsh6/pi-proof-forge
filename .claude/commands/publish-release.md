---
name: "Publish Release"
description: Publish this project release in one command (GitFlow + tag + GitHub Release)
category: Release
tags: [gitflow, release, github]
---

Publish this repository with the project release flow.

Usage:

```text
/publish-release <feature> <release> <version> <notes-file>
```

Example:

```text
/publish-release aief-single-directory-release v0.1.1 v0.1.1 release-notes/v0.1.1.md
```

Execution steps:

1. Validate input has exactly four values: `feature`, `release`, `version`, `notes-file`
2. Run:

```bash
python3 tools/run_github_publish.py --feature "<feature>" --release "<release>" --version "<version>" --release-notes-file "<notes-file>"
```

3. Return release URL from command output

Guardrails:
- Do not skip checks unless user explicitly asks (`--skip-check`)
- Do not force push main
- Do not publish without release notes unless user explicitly asks to use `--allow-generate-notes`
- If publish fails with transient GitHub 5xx, retry up to 3 times before failing
