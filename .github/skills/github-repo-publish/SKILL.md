---
name: github-repo-publish
description: Project-specific skill for publishing this repository to GitHub with repeatable release operations (gitflow promotion, tagging, GitHub release).
---

# Publish This Repository to GitHub

## Direct Invocation

Use one command to execute publish flow:

```bash
python3 tools/run_github_publish.py --feature <feature> --release <release> --version <version>
```

## When to Use

Use this skill when the user asks to:
- publish/open-source this repo
- prepare a version release
- create a GitHub release from current code
- run project GitFlow promotion for release

## Required Checks

Run these before any release action:

1. `python3 tools/check_aief_l3.py --root .`
2. Ensure working tree is clean (`git status -sb`)
3. Verify `README.md` and `LICENSE` exist

## AIEF Single-Directory Mode

When retrofitting AIEF assets into a dedicated base folder:

```bash
npx --yes @tongsh6/aief-init@latest retrofit --level L1 --base-dir AIEF
```

Expected directories:
- `AIEF/context/`
- `AIEF/workflow/`
- `AIEF/docs/standards/`
- `AIEF/templates/`
- `AIEF/scripts/`

## Branch and Release Flow

Project release flow:

```text
main -> feature -> develop -> release -> main
```

Branch retention policy:
- delete merged `feature/*`
- keep `release/*`

Use the project script:

```bash
python3 tools/run_gitflow_release.py --feature <topic> --release <version> --create-feature
```

Preview without execution:

```bash
python3 tools/run_gitflow_release.py --feature <topic> --release <version> --create-feature --dry-run
```

## GitHub Release Steps

After code promotion to `main`:

```bash
git checkout main
git pull --ff-only origin main
git tag vX.Y.Z
git push origin vX.Y.Z
gh release create vX.Y.Z --title "vX.Y.Z" --generate-notes
```

## Guardrails

- Never force push `main`
- Never publish secrets (`.env*`, credentials, keys)
- Never skip release verification commands
