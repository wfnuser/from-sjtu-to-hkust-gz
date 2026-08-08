# Static Deployment Hygiene Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the repository understandable, secret-safe, and ready for deployment as a portable static site without committing to a hosting vendor.

**Architecture:** Treat `web/` as the deployable artifact directory and the Python package/scripts as the private generation toolchain. Document local preview, deterministic verification, environment configuration, and the hosting contract while keeping secrets and API caches ignored.

**Tech Stack:** Git, Markdown, dotenv convention, Python static HTTP server

## Global Constraints

- Do not push, create a remote, or create a production deployment without explicit authorization.
- Do not commit `.env.local`, API keys, generated caches, Python bytecode, or worktrees.
- Hosting must require no build step and must publish the existing `web/` directory.
- Do not add a vendor-specific deployment configuration until the user chooses a host.

---

### Task 1: Document the repository and hosting contract

**Files:**
- Create: `.env.example`
- Modify: `README.md`

**Interfaces:**
- Consumes: `.gitignore`, `web/`, `scripts/generate_route.py`, and existing deterministic tests.
- Produces: a safe environment template and exact local/deployment instructions.

- [ ] **Step 1: Add the safe environment template**

```dotenv
# 高德 Web 服务 API Key；复制为 .env.local 后填写真实值。
AMAP_WEB_SERVICE_KEY=
```

- [ ] **Step 2: Rewrite README around the actual project lifecycle**

Document these exact sections:

- current status: coastal route published, inland route awaiting live routing quota;
- local preview: `python3 -m http.server 8765 --bind 127.0.0.1 --directory web`;
- deterministic verification command that excludes the live smoke test;
- optional live smoke command and `.env.local` setup;
- deployment contract: no build command, publish directory `web`, SPA fallback not required;
- Git policy: route artifacts and configuration are tracked, secrets and API cache are ignored.

- [ ] **Step 3: Verify secret hygiene and docs accuracy**

Run: `git check-ignore -v .env.local cache/probe.json`

Expected: both paths are ignored.

Run: `git grep -nE 'AMAP_WEB_SERVICE_KEY=[^[:space:]]+' -- ':!tests/**' ':!.env.example'`

Expected: no matches.

Run: `python3 -m http.server 8766 --bind 127.0.0.1 --directory web`

Expected: `web/index.html`, CSS, JavaScript, and data artifacts return successfully.

- [ ] **Step 4: Commit deployment documentation**

```bash
git add .env.example README.md
git commit -m "docs: prepare static deployment"
```

### Task 2: Reconcile the existing inland work without mixing concerns

**Files:**
- Modify: `config/inland-route.json`
- Modify: `route_planner/export.py`
- Modify: `scripts/generate_route.py`
- Create: `tests/test_inland_route.py`

**Interfaces:**
- Consumes: the existing uncommitted inland schedule and generation-readiness work.
- Produces: one verified commit that preserves incomplete route status without publishing fabricated geometry.

- [ ] **Step 1: Review the existing diff and confirm no route artifact is being published**

Run: `git diff -- config/inland-route.json route_planner/export.py scripts/generate_route.py && test ! -e web/data/inland-route.geojson`

Expected: only inland configuration/schedule support is present, and no inland geometry artifact exists.

- [ ] **Step 2: Run the inland acceptance and regression tests**

Run: `python3 -m unittest tests.test_inland_route tests.test_export tests.test_audit -v`

Expected: all tests PASS without live API traffic.

- [ ] **Step 3: Commit the offline inland contract separately**

```bash
git add config/inland-route.json route_planner/export.py scripts/generate_route.py tests/test_inland_route.py
git commit -m "feat: prepare inland route generation"
```

### Task 3: Record remote and deployment decisions later

**Files:**
- No files changed until the user selects a Git host and deployment platform.

**Interfaces:**
- Consumes: a user-provided repository destination and hosting choice.
- Produces: an explicit remote configuration and, only if requested, vendor-specific deployment automation.

- [ ] **Step 1: Report that no remote is configured**

Run: `git remote -v`

Expected: no output.

- [ ] **Step 2: Ask for the Git repository URL and preferred host before any external action**

Do not call `git remote add`, `git push`, or a hosting API until the user supplies or approves the target.
