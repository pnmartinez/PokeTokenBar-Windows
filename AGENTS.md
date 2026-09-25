# Repository collaboration rules

These instructions apply to every human or agent working anywhere in this repository. The repository is shared by multiple contributors, so GitHub must reflect active work closely enough that nobody unknowingly duplicates or overwrites it.

## Shared source of truth

- Treat the `origin` remote on GitHub as the shared source of truth. Active branches and useful commits must not remain local-only.
- Preserve uncommitted work already present in the checkout. Never reset, discard, overwrite, or fold it into another change without first identifying its owner and intent.
- Never implement directly on `master`. Use a focused feature or fix branch.

## Before starting any work

1. Run `git fetch --prune origin`.
2. Inspect `git status --short --branch`, `git branch -vv`, and the recent remote branches.
3. Confirm the intended base contains the latest `origin/master`. Before creating a new branch, local `master` and `origin/master` must not have unknown divergence.
4. Check open pull requests when GitHub CLI is available (`gh pr list --state open`) and inspect unmerged remote branches (`git branch -r --no-merged origin/master`).
5. Look for overlapping work by comparing the paths changed on relevant branches, for example `git diff --name-only origin/master...origin/<branch>`.
6. If another branch or PR touches the same feature, UI surface, data model, or files, stop and coordinate before editing. Agree whether to share that branch, split ownership by path, rebase on it, or wait for it to merge.

Do not assume work is absent merely because it is not on `master`.

## Branch publication

- Use a descriptive branch name. Codex-created branches use `codex/<short-scope>`; when ownership is useful for coordination, prefer `codex/<owner>-<short-scope>`.
- Publish a newly created branch immediately with `git push -u origin HEAD`, before substantial implementation begins.
- If a branch has no unique commit yet, it is still valid to publish its current pointer; follow it promptly with the first coherent commit.
- Never delete a remote branch that may contain active work without explicit coordination.

## Commits and pushes

- Make small, coherent commits at meaningful checkpoints. Do not wait until the whole feature is perfect before creating the first visible checkpoint.
- Push every commit immediately after it is created. A commit that exists only locally is not a coordination mechanism.
- If work must stop in an incomplete but safe state, create a clearly described checkpoint commit, push it, and document what remains.
- Use commit messages that identify the behavior or area changed; avoid vague messages such as `updates` or `fix stuff`.
- Never force-push or rewrite a published branch that somebody else may have based work on unless all affected contributors explicitly agree.

## Staying synchronized during work

- Fetch again before broad or high-conflict edits and before integrating or handing off work.
- Recheck active branches and PRs when the scope expands beyond the branch's original purpose.
- Keep unrelated changes out of the branch. If a new concern is independent, publish a separate branch.
- When incorporating someone else's work, preserve attribution and prefer normal merge/rebase workflows over copying code without history.

## Pull requests

- Publishing the branch is mandatory; opening a draft PR is situational.
- Open a draft PR early when work spans multiple sessions, touches shared hotspots, changes architecture or broad UI, needs early feedback, or may be continued by another contributor.
- A short, isolated change may remain as a published branch until it is ready for a normal PR.
- Keep PR descriptions current with scope, completed work, remaining work, tests run, blockers, and known overlapping branches.

## Handoffs and completion

- Before handing work to another person or agent, commit and push every intended change.
- Report the branch name, latest commit hash, validation performed, and any unfinished or risky areas. If a PR exists, put the same status there.
- Confirm `git status --short --branch` shows the branch tracking its remote and no unexplained local commits remain.
- Before marking a change ready to merge, fetch `origin`, integrate the latest `origin/master`, resolve conflicts deliberately, run validation, and push the result.

## Project validation

For Python changes, use the project virtual environment on Windows when available:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q src tests
git diff --check
```

Use the equivalent active Python environment on other platforms. Document any check that could not be run.

## Local build retention

- Use scripts/build-exe.ps1 for local EXE builds. It writes the latest local master build to dist/PokeTokenBar-Windows and reuses one dist/branches/<branch-slot>/PokeTokenBar-Windows directory per active branch across worktrees.
- Do not create date-, commit-, or PR-named full copies in dist by default. Keep an older comparison build only when explicitly needed; record why and remove it after that comparison.
- After a merge, update local master, build and verify its EXE, then remove the merged branch build. A successful local master build runs scripts/prune-dist.ps1 -Apply to remove managed builds whose branches are merged. It leaves unrecognized folders untouched.
- Before calling a local build the latest version, compare its build-info.json commit with the relevant branch tip. GitHub Actions artifacts do not automatically update this machine's dist.
- Never remove an installed application or user save data as part of build cleanup.
