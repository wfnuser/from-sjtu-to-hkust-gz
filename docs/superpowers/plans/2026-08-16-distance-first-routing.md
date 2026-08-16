# Distance-First Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make route selection distance-first, retain hard safety exclusions, and publish a Day 3 route of roughly 134–136 km through the 富春 and 新安 greenways.

**Architecture:** Candidate ranking in `route_planner/roads.py` will filter effective hard/freight risks before comparing distance. A segment-scoped, evidence-backed safe-step override will handle AMap's 60 m `新安江互通` label where OpenStreetMap records a continuous designated asphalt cycleway; ordinary national-road distance will no longer block publication. The existing generator will rebuild all execution artifacts from the revised policy and Day 3 anchors.

**Tech Stack:** Python 3 standard library, `unittest`, AMap Web Service cache/API, static Leaflet JavaScript, JSON/GeoJSON.

## Global Constraints

- Default to the shortest eligible route.
- Never select freight-risk steps.
- Never select hard-risk steps unless a segment-scoped exact road/distance override has public road-level evidence.
- Prefer a parallel non-national route only when explicitly configured and no more than 2,000 m longer than the shortest eligible route.
- Day 3 must retain `捷安特自行车（桐庐店）`, `富春江镇`, and `新安绿道洋溪段`, and target 134–136 km total.
- Do not export GPX.

---

### Task 1: Distance-first candidate ranking

**Files:**
- Modify: `route_planner/models.py`
- Modify: `route_planner/roads.py`
- Modify: `route_planner/config.py`
- Modify: `route_planner/manifest.py`
- Test: `tests/test_roads.py`
- Test: `tests/test_config.py`
- Test: `tests/test_manifest.py`

**Interfaces:**
- Produces: `SegmentRule.parallel_road_max_extra_m: int` with default `0`.
- Produces: `choose_candidate(candidates, rule) -> CandidateRoute` that ranks by distance after safety filtering.

- [x] **Step 1: Add failing ranking tests**

Add tests proving that a 72,638 m candidate with 1,173 m national road beats a 79,939 m candidate with 1,106 m national road, while an explicitly configured parallel-road candidate may win only within `parallel_road_max_extra_m=2_000`.

- [x] **Step 2: Run the focused tests and verify the current national-first order fails**

Run: `python3 -m unittest tests.test_roads.CandidateSelectionTests -v`

- [x] **Step 3: Implement distance-first ranking and config/manifest round-trip**

Filter freight and effective hard risks first. Build the pool from all safe candidates; only narrow it to candidates at or below `allowed_national_m` when `parallel_road_available` is true, `parallel_road_max_extra_m > 0`, and a compliant candidate is no more than that threshold longer than the shortest safe candidate. Select the remaining minimum by `(distance_m, duration_s, source_index)`.

- [x] **Step 4: Run focused road, config, and manifest tests**

Run: `python3 -m unittest tests.test_roads tests.test_config tests.test_manifest -v`

### Task 2: Evidence-backed safe cycleway override

**Files:**
- Modify: `route_planner/models.py`
- Modify: `route_planner/roads.py`
- Modify: `route_planner/config.py`
- Modify: `route_planner/manifest.py`
- Modify: `route_planner/planner.py`
- Modify: `scripts/audit_route.py`
- Test: `tests/test_roads.py`
- Test: `tests/test_config.py`
- Test: `tests/test_manifest.py`
- Test: `tests/test_audit.py`

**Interfaces:**
- Produces: immutable `VerifiedSafeStep(road_name: str, max_distance_m: int, evidence_url: str, evidence_note: str)`.
- Produces: `SegmentRule.verified_safe_steps: tuple[VerifiedSafeStep, ...]`.
- Produces: `effective_risk_tags(step, verified_safe_steps) -> frozenset[str]` used by both selection and audit.

- [x] **Step 1: Add failing tests for exact scoped overrides**

Cover an exact `新安江互通` 60 m hard step cleared by an HTTPS-evidenced override, a 61 m step that remains hard, a different road name that remains hard, manifest round-trip, and config rejection of missing evidence.

- [x] **Step 2: Run focused tests and verify the override schema is absent**

Run: `python3 -m unittest tests.test_roads tests.test_config tests.test_manifest tests.test_audit -v`

- [x] **Step 3: Implement the model, parsing, manifest, metrics, planner, and audit support**

Only remove the `hard` tag when the step road name exactly matches and its distance is at most the configured bound. Do not clear `freight`. Require a non-empty note and an `https://` evidence URL.

- [x] **Step 4: Stop treating ordinary national-road distance as a publication blocker**

Remove ordinary `NATIONAL_ROAD_ALLOWANCE_EXCEEDED` and `NATIONAL_ROAD_EXCEPTION_UNREVIEWED` findings. Keep route generation's explicit near-distance parallel-road choice, but do not make national-road presence itself a hard audit finding.

- [x] **Step 5: Run the focused suite**

Run: `python3 -m unittest tests.test_roads tests.test_config tests.test_manifest tests.test_planner tests.test_audit -v`

### Task 3: Publish the corrected Day 3 route

**Files:**
- Modify: `config/inland-execution-route.json`
- Modify: `config/inland-itinerary.json`
- Modify: `tests/test_execution_itinerary.py`
- Regenerate: `web/data/inland-execution-route.geojson`
- Regenerate: `web/data/inland-execution-route-manifest.json`
- Regenerate: `web/data/inland-execution-summary.json`
- Regenerate: `web/data/inland-execution-review.md`
- Regenerate: `web/data/inland-itinerary.json`

**Interfaces:**
- Consumes: distance-first selection and verified safe-step override from Tasks 1–2.
- Produces: Day 3 execution data with anchors `桐庐县富春江镇` and `杭州::建德市新安绿道洋溪段`.

- [x] **Step 1: Add failing Day 3 contract assertions**

Assert key waypoints are `捷安特自行车（桐庐店）`, `富春江镇`, and `新安绿道洋溪段`; generated Day 3 distance is between 134,000 and 136,000 m; the published route has no unresolved hard-risk review.

- [x] **Step 2: Run the execution tests and verify they fail against the 141.2 km artifact**

Run: `python3 -m unittest tests.test_execution_itinerary -v`

- [x] **Step 3: Update Day 3 config**

Add `杭州::建德市新安绿道洋溪段` after `桐庐县富春江镇`. Replace the old hard-risk allowance with a 60 m verified-safe override for `新安江互通`, using `https://www.openstreetmap.org/way/1376423198` and a note that the mapped parallel facility is a continuous designated asphalt cycleway. Remove the 60 m push/walk risk note from the itinerary.

- [x] **Step 4: Regenerate route and itinerary artifacts**

Run `scripts/generate_route.py` with the execution config, stored resolutions, `.env.local`, `.cache/amap`, and `web/data`, then run `scripts/export_itinerary.py`. Do not run a GPX exporter.

- [x] **Step 5: Run the execution tests and inspect Day 3 metrics**

Run: `python3 -m unittest tests.test_execution_itinerary -v`

Inspect: `jq '.days[] | select(.day==3)' web/data/inland-itinerary.json`

### Task 4: Remove avoid-national framing from the public UI

**Files:**
- Modify: `web/index.html`
- Modify: `web/app.mjs`
- Modify: `README.md`
- Modify: `tests/test_web_contract.py`

**Interfaces:**
- Produces: public copy describing `近距离安全备选` rather than `避国道备选`.

- [x] **Step 1: Add failing UI copy and cache-version assertions**

Require the new safety-alternative copy, reject `避国道备选`, and bump execution static asset cache version to `20260816-2`.

- [x] **Step 2: Run the web contract tests and verify failure**

Run: `python3 -m unittest tests.test_web_contract -v`

- [x] **Step 3: Update copy, cache versions, and README policy/status**

State that national roads are accepted when they are the materially shorter eligible route. Keep specific road-risk facts and original-route comparison controls.

- [x] **Step 4: Run web contract and JavaScript syntax checks**

Run: `python3 -m unittest tests.test_web_contract -v`

Run: `node --check web/app.mjs`

### Task 5: Full verification and publication

**Files:**
- Verify all modified and generated files.

- [x] **Step 1: Run the complete offline suite excluding the live AMap smoke test**

Run the test modules documented in `README.md`; expected result is zero failures.

- [x] **Step 2: Run strict execution-route audit**

Run: `python3 scripts/audit_route.py --config config/inland-execution-route.json --data-dir web/data --env .env.local --profile execution --strict`

- [x] **Step 3: Run final hygiene checks**

Run: `git diff --check`, `node --check web/app.mjs`, verify `.env.local` is untracked, and inspect Day 3 distance, anchors, reviews, and selected route indices.

- [x] **Step 4: Commit and push**

Commit implementation and generated artifacts with `feat: switch route planning to distance first`, push `main`, and verify `HEAD` equals `origin/main` with a clean worktree.
