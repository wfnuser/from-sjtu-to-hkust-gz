# Balanced Day 5–15 Route Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the execution route so Day 4 is the roughly 114 km direct Jiande–Changshan ride and Day 5–15 form eleven evenly sized riding days ending at HKUST(GZ), each at or below 115 km.

**Architecture:** Keep Day 0–3 immutable, replace the Day 4–14 waypoint chain with lodging endpoints selected on the distance-first corridor, and let each adjacent lodging pair be one execution segment. AMap remains the source of route geometry and duration; the itinerary config remains the source of day assignment, lodging evidence, and public day-card copy.

**Tech Stack:** Python 3 standard library, `unittest`, AMap Web Service with local cache, JSON/GeoJSON, static Leaflet JavaScript.

## Global Constraints

- Preserve all Day 0–3 route segments and itinerary facts.
- Day 4 starts at 麗枫酒店（杭州建德新安江店） and ends at 常山东方广场酒店 using the shortest eligible route, targeting roughly 114 km.
- Day 5–15 are exactly eleven riding days; Day 15 ends at 香港科技大学（广州）.
- Each Day 5–15 distance must be at most 115,000 m and should target 105,000–113,000 m.
- Day 5–14 lodging may change, but every night requires HTTPS evidence of self-service laundry and suitable lodging conditions.
- Do not add lunch or charging anchors in this pass.
- Do not retain a city or town solely to avoid national roads; unresolved hard and freight risks remain ineligible.
- Do not export GPX.

---

### Task 1: Lock the new day and distance contracts

**Files:**
- Modify: `tests/test_execution_itinerary.py`
- Modify: `tests/test_day_card_model.py`

**Interfaces:**
- Consumes: `config/inland-itinerary.json` and generated `web/data/inland-itinerary.json`.
- Produces: regression contracts for Day 0–15, Day 4 directness, Day 5–15 distance caps, arrival day, and lodging evidence.

- [ ] **Step 1: Add failing itinerary assertions**

Assert that day IDs are `0..15`, Day 4 has one lodging-to-lodging segment with no required intermediate waypoints, Day 5–15 contains eleven entries, every Day 5–15 distance is `<= 115_000`, and Day 15 ends at 香港科技大学（广州）.

- [ ] **Step 2: Add public-card assertions**

Assert that the visible itinerary remains Day 1–15 while Day 0 stays hidden.

- [ ] **Step 3: Run the focused tests and verify failure**

Run: `python3 -m unittest tests.test_execution_itinerary tests.test_day_card_model -v`

Expected: failures because the current itinerary ends on Day 14 and contains multiple days above 115 km.

### Task 2: Replace the remaining corridor with lodging endpoints

**Files:**
- Modify: `config/inland-execution-route.json`
- Modify: `config/inland-execution-poi-resolutions.json`
- Modify: `config/inland-itinerary.json`

**Interfaces:**
- Consumes: AMap geocoding/electrobike results, the fixed Day 4 endpoints, and the 115 km contract.
- Produces: a contiguous lodging-to-lodging route from 建德 through 常山 to HKUST(GZ), with one segment per Day 4–15.

- [ ] **Step 1: Establish the Day 4 direct segment**

Remove 龙游、衢州、寿昌、詹家、高家 as forced Day 4 waypoints/anchors. Plan 麗枫酒店（杭州建德新安江店） directly to 常山东方广场酒店 and retain the shortest eligible AMap candidate.

- [ ] **Step 2: Measure the distance-first Day 5–15 corridor**

Probe candidate lodging towns at cumulative 105–113 km intervals from 常山. Reject a candidate if it makes either adjacent day exceed 115 km, materially detours from the direct corridor, or lacks a usable hotel with self-service laundry evidence.

- [ ] **Step 3: Select and resolve ten nightly hotels**

Choose Day 5–14 hotel POIs, record their exact AMap selected candidates in `config/inland-execution-poi-resolutions.json`, and attach an HTTPS hotel/brand evidence URL plus `laundry: confirmed` in `config/inland-itinerary.json`.

- [ ] **Step 4: Remove obsolete forced waypoints and rules**

Delete old city/town endpoints and anchor queries that are not selected lodging endpoints. Create one explicit `SegmentRule` per adjacent lodging pair, assign days 4–15, and keep only evidence-backed safety metadata required by the selected geometry.

- [ ] **Step 5: Validate configuration loading**

Run: `python3 -m unittest tests.test_config tests.test_execution_itinerary.ExecutionItineraryContractTests -v`

### Task 3: Regenerate and publish the balanced itinerary

**Files:**
- Regenerate: `web/data/inland-execution-route.geojson`
- Regenerate: `web/data/inland-execution-route-manifest.json`
- Regenerate: `web/data/inland-execution-summary.json`
- Regenerate: `web/data/inland-execution-review.md`
- Regenerate: `web/data/inland-itinerary.json`
- Modify: `README.md`
- Modify: `web/route-profile.mjs`
- Modify: `web/index.html`
- Modify: `web/app.mjs`

**Interfaces:**
- Consumes: the resolved route and itinerary configs from Task 2.
- Produces: deployable Day 1–15 map data and copy.

- [ ] **Step 1: Regenerate execution route artifacts**

Run:

```bash
python3 scripts/generate_route.py \
  --config config/inland-execution-route.json \
  --resolutions config/inland-execution-poi-resolutions.json \
  --env .env.local \
  --cache-dir .cache/amap \
  --output-dir web/data \
  --profile execution
```

- [ ] **Step 2: Export the Day 0–15 itinerary**

Run:

```bash
python3 scripts/export_itinerary.py \
  --config config/inland-itinerary.json \
  --manifest web/data/inland-execution-route-manifest.json \
  --geojson web/data/inland-execution-route.geojson \
  --output web/data/inland-itinerary.json
```

- [ ] **Step 3: Inspect and adjust outliers**

Use `jq` to inspect Day 4–15 distances. If any Day 5–15 exceeds 115,000 m, move the adjacent lodging endpoint along the same corridor and regenerate; do not solve an outlier with a detour anchor.

- [ ] **Step 4: Update public copy and cache versions**

Publish Day 1–15 wording, the new total/remaining/average distance, and the actual longest day. Bump the static cache version in `web/index.html` and module imports.

- [ ] **Step 5: Run focused itinerary and web tests**

Run: `python3 -m unittest tests.test_execution_itinerary tests.test_day_card_model tests.test_route_profile tests.test_web_contract -v`

Run: `node --check web/app.mjs`

### Task 4: Verify and publish

**Files:**
- Verify all modified and generated files.

**Interfaces:**
- Consumes: the complete balanced route implementation.
- Produces: a clean, audited `main` branch synchronized with `origin/main`.

- [ ] **Step 1: Run the complete offline test suite**

Run the full module list documented in `README.md`, excluding only `AmapLiveSmokeTest`; expected result is zero failures.

- [ ] **Step 2: Run strict execution audit and hygiene checks**

Run:

```bash
python3 scripts/audit_route.py \
  --config config/inland-execution-route.json \
  --data-dir web/data \
  --env .env.local \
  --profile execution \
  --strict
node --check web/app.mjs
git diff --check
```

- [ ] **Step 3: Verify the final metrics**

Confirm Day 4 is roughly 114 km, all Day 5–15 distances are at most 115 km, Day 15 ends at HKUST(GZ), every planned night has laundry evidence, and no unresolved hard/freight review is published.

- [ ] **Step 4: Commit and push**

Commit implementation and generated artifacts to `main`, push `origin main`, and verify a clean worktree with `HEAD == origin/main`.
