# Live Deploy Runbook

Last updated: 2026-07-09

## Purpose

This is the only normal deployment path for Tradamind live.

Use this when shipping normal code changes:

1. build locally
2. push to GitHub `main`
3. GitHub Actions deploys live

No manual server deploy. No staging detour. No direct server code editing.

## Golden Path

Run from the project root:

```bash
cd /Users/gvangalen/Documents/antigravity-trading-tool
```

Check what changed:

```bash
/usr/bin/git status --short
```

Run frontend checks:

```bash
cd frontend/trading-tool-frontend
npm run test:i18n
npm run build
```

Return to root:

```bash
cd /Users/gvangalen/Documents/antigravity-trading-tool
```

Stage only intended files:

```bash
/usr/bin/git add <files>
```

Commit:

```bash
/usr/bin/git commit -m "Short clear commit message"
```

Push to live deploy branch:

```bash
/usr/bin/git push origin main
```

GitHub Actions will deploy live automatically from `main`.

## If Current Branch Is Not Main

Do not push a feature branch and expect live deploy.

Use a temporary clean `main` worktree or merge/cherry-pick onto `main`, then run the golden path.

Preferred quick path:

```bash
git worktree add /private/tmp/tradamind-main-deploy main
cd /private/tmp/tradamind-main-deploy
/usr/bin/git pull --ff-only origin main
/usr/bin/git cherry-pick <commit>
cd frontend/trading-tool-frontend
npm run test:i18n
npm run build
cd /private/tmp/tradamind-main-deploy
/usr/bin/git add <files>
/usr/bin/git commit -m "Refresh frontend export if needed"
/usr/bin/git push origin main
```

Use `/usr/bin/git` for pushes because the bundled git may not have GitHub credentials.

## What Not To Do

- Do not manually SSH into live for normal frontend/backend deploys.
- Do not deploy from staging unless the task is explicitly a staging task.
- Do not push only a `codex/*` branch and assume live changed.
- Do not edit generated `out/` conflicts manually.
- Do not claim live is updated until `main` has been pushed and Actions has had time to run.

## Generated Frontend Export

The frontend build regenerates `frontend/trading-tool-frontend/out`.

If `out/` conflicts during cherry-pick or merge:

```bash
rm -rf frontend/trading-tool-frontend/out
cd frontend/trading-tool-frontend
npm run build
cd /path/to/worktree
/usr/bin/git add frontend/trading-tool-frontend/out
```

Do not hand-edit generated files.

## Quick Verification

After push:

1. Open GitHub Actions and confirm the `main` deploy run started.
2. Wait until the run is green.
3. Open `https://www.tradamind.com/api/health`.
4. Open `https://www.tradamind.com`.
5. If a release commit endpoint exists, verify live commit equals the pushed `main` commit.

## One-Minute Mental Model

The deploy is:

```text
local build/test -> git push origin main -> GitHub Actions -> live server
```

Anything else is an exception, not the default.
