# Fifteen-Day Route Constraint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce a maximum of 15 riding days and stop presenting infeasible route partitions as an executable itinerary.

**Architecture:** Add the riding-day cap to the existing schedule contract while preserving the 18-calendar-day deadline window. Keep diagnostic `days` data in JSON, but let the static UI replace infeasible daily details and day headings with one decision warning.

**Tech Stack:** Python 3, `unittest`, static JavaScript, JSON artifacts

## Global Constraints

- Maximum riding days is exactly 15.
- The date window remains 2026-08-13 through 2026-08-30 inclusive: 18 calendar days and 3 buffer days.
- Every day retains four work hours and no planned riding day exceeds six hours.
- Do not alter route geometry, road classification, review findings, or optional branches.
- Infeasible diagnostic partitions remain in JSON but are not rendered as an executable daily plan.

---

### Task 1: Enforce the backend schedule contract

**Files:**
- Modify: `route_planner/export.py`
- Modify: `tests/test_inland_route.py`
- Modify: `tests/test_export.py`
- Modify: `config/inland-route.json`
- Modify: `scripts/generate_route.py`

**Interfaces:**
- Produces: `summary.schedule.max_riding_days`, `buffer_days`, and feasibility based on `len(days) <= 15`.

- [ ] Add failing tests proving 15 days is feasible, 16 is infeasible, the natural-day window remains 18, and buffer days equal 3.
- [ ] Update `_schedule_contract()` with `_MAX_RIDING_DAYS = 15`; compute `buffer_days = available_days - 15`; require both the riding-day cap and daily time constraints.
- [ ] Make deadline notes state the required day count and 15-day maximum when infeasible.
- [ ] Preserve existing inland generation-readiness work and verify no inland route artifact is published without live geometry.
- [ ] Run `python3 -m unittest tests.test_inland_route tests.test_export tests.test_audit -v` and the full deterministic suite.
- [ ] Commit the backend and existing inland offline contract as `feat: enforce fifteen-day route schedule`.

### Task 2: Render infeasibility as a decision, not a plan

**Files:**
- Modify: `web/app.mjs`
- Modify: `tests/test_web_contract.py`
- Regenerate: `web/data/summary.json`
- Regenerate: `web/data/review.md`
- Verify unchanged: `web/data/coastal-route.geojson`, `web/data/route-manifest.json`

**Interfaces:**
- Consumes: `summary.schedule.deadline_feasible`, `day_count`, and `max_riding_days`.
- Produces: an infeasible warning in `#daily-schedule`; day headings only for feasible schedules.

- [ ] Add failing web contract tests for the 15-day decision copy and conditional day rendering.
- [ ] In `renderDailySchedule()`, set the count to `需要 ${dayCount} 天 · 上限 ${maxDays} 天` and render one warning when infeasible: `当前路线需要 ${dayCount} 个骑行日，超过 ${maxDays} 天上限 ${dayCount - maxDays} 天；不作为执行方案。`
- [ ] In `renderSegmentCards()`, skip `.day-heading` creation when `deadline_feasible` is false.
- [ ] Load `web/data/route-manifest.json` with `load_manifest()`, rebuild coastal summary/review through `generate_from_segments(..., profile="coastal")`, and verify GeoJSON/manifest hashes did not change.
- [ ] Run `python3 -m unittest tests.test_web_contract tests.test_artifacts tests.test_audit tests.test_export tests.test_inland_route -v` and the full deterministic suite.
- [ ] Verify the browser shows `需要 32 个骑行日 · 上限 15 天` without a 32-item itinerary.
- [ ] Commit as `fix: enforce fifteen-day route decision`.
