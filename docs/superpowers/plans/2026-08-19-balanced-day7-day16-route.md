# Balanced Day 7–16 Route Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the execution itinerary so Day 7–15 are balanced at 95–102 km, Day 16 is a short 15–35 km arrival ride, and every night uses acceptable lodging without fixed intermediate stops.

**Architecture:** Keep Day 0–6 and the Day 7 start fixed, then replace the Day 7–15 lodging boundaries using cumulative AMap cycling distance along the existing Jiangxi–northeast Guangdong corridor. The itinerary remains the source of day assignment and lodging evidence, while AMap remains the source of route geometry and duration; only the `execution` profile receives a 16-day schedule allowance.

**Tech Stack:** Python 3 standard library, `unittest`, AMap Web Service with local cache, JSON/GeoJSON, static Leaflet JavaScript with AMap raster tiles.

## Global Constraints

- Preserve all Day 0–6 route segments, itinerary facts, dates, and published geometry.
- Day 7 starts at 鹰潭枫丹白露酒店（雲锦君澜）; Day 16 ends at 香港科技大学（广州） on 2026-08-29.
- **Each Day 7–15 distance must be ≤ 100,000 m (no 100–102 km grace band).**
- Day 16 must be 15,000–35,000 m and should target roughly 25,000 m.
- Day 7–16 must have empty `key_waypoints`; no fixed lunch, charging, or rest stops are introduced.
- Prefer the shortest eligible AMap cycling candidate; do not add detours solely to hit a round-number distance.
- Every Day 7–15 lodging needs an HTTPS evidence URL and `laundry: confirmed` or `laundry: call_required`.
- Do not use 汉庭 or 7 天 as a planned lodging endpoint.
- Preserve the 15-day cap for `coastal` and `inland`; allow 16 riding days only for `execution`.
- Do not export GPX.

---

### Task 1: Lock the Day 7–16 itinerary contract

**Files:**
- Modify: `tests/test_execution_itinerary.py`
- Modify: `tests/test_day_card_model.py`
- Modify: `tests/test_route_profile.py`
- Modify: `tests/test_web_contract.py`

**Interfaces:**
- Consumes: `config/inland-itinerary.json`, `web/data/inland-itinerary.json`, `web/route-profile.mjs`.
- Produces: regression contracts for Day 0–16, dates, distance ranges, direct daily segments, lodging evidence, and Day 1–16 public copy.

- [ ] **Step 1: Write the failing itinerary-shape test**

Update `test_fixed_actual_and_planned_days_are_not_reassigned` so the expected day IDs are `list(range(17))`, Day 6 still ends at 鹰潭枫丹白露酒店（雲锦君澜）, and Day 16 ends at 香港科技大学（广州） with date `2026-08-29`.

- [ ] **Step 2: Write the failing distance and directness test**

Replace the current Day 6–15 range assertion with:

```python
balanced_days = [day for day in published["days"] if 7 <= day["day"] <= 15]
self.assertEqual(len(balanced_days), 9)
self.assertTrue(all(day["distance_m"] <= 100_000 for day in balanced_days))
day16 = next(day for day in published["days"] if day["day"] == 16)
self.assertTrue(15_000 <= day16["distance_m"] <= 35_000)
self.assertTrue(all(day.get("key_waypoints", []) == [] for day in published["days"] if 7 <= day["day"] <= 16))
```

- [ ] **Step 3: Write the failing lodging-quality test**

Make planned-night selection use `day < 16`, require HTTPS evidence and a laundry status for Day 7–15, and assert that no Day 7–15 lodging name contains `汉庭` or `7天`.

- [ ] **Step 4: Write the failing public-card and copy tests**

Change the day-card fixture to contain Day 0–16 and expect visible IDs `1..16`. Expect `web/route-profile.mjs` to expose `mainLabel: "Day 1–16 执行路线"`, and expect README/web contract copy to say Day 1–16.

- [ ] **Step 5: Run the focused tests and verify RED**

Run:

```bash
python3 -m unittest \
  tests.test_execution_itinerary.ExecutionItineraryContractTests \
  tests.test_day_card_model \
  tests.test_route_profile \
  tests.test_web_contract -v
```

Expected: failures showing that the current itinerary stops at Day 15 and the public label still says Day 1–15.

### Task 2: Make the schedule limit profile-specific

**Files:**
- Modify: `route_planner/export.py`
- Modify: `tests/test_inland_route.py`
- Modify: `tests/test_export.py`

**Interfaces:**
- Consumes: `_schedule_contract(days, profile)`.
- Produces: profile-aware `max_riding_days`, `buffer_days`, `deadline_feasible`, and `deadline_note` fields.

- [ ] **Step 1: Write the failing execution-profile schedule test**

Add a test that builds 16 six-hour-or-less schedule segments with `profile="execution"` and asserts:

```python
self.assertEqual(summary["schedule"]["max_riding_days"], 16)
self.assertEqual(summary["schedule"]["buffer_days"], 2)
self.assertTrue(summary["schedule"]["deadline_feasible"])
self.assertIn("16个骑行日完成", summary["schedule"]["deadline_note"])
```

- [ ] **Step 2: Preserve the legacy 15-day tests**

Keep `test_inland_schedule_rejects_sixteen_riding_days_despite_eighteen_natural_days` unchanged so `profile="inland"` still reports `max_riding_days == 15`, `buffer_days == 3`, and `deadline_feasible is False`.

- [ ] **Step 3: Run schedule tests and verify RED**

Run: `python3 -m unittest tests.test_inland_route tests.test_export -v`

Expected: only the new execution-profile 16-day test fails because `_MAX_RIDING_DAYS` is globally fixed at 15.

- [ ] **Step 4: Implement the profile-aware limit**

Replace the single limit lookup inside `_schedule_contract` with an explicit mapping:

```python
max_riding_days = {
    "coastal": 15,
    "inland": 15,
    "execution": 16,
}[profile]
buffer_days = available_days - max_riding_days
```

Use `max_riding_days` consistently in feasibility checks, notes, and the returned `max_riding_days` field. Do not change the deadline dates or six-hour riding constraint.

- [ ] **Step 5: Run schedule tests and verify GREEN**

Run: `python3 -m unittest tests.test_inland_route tests.test_export -v`

Expected: all tests pass; only `execution` accepts 16 riding days.

- [ ] **Step 6: Commit the schedule contract**

```bash
git add route_planner/export.py tests/test_inland_route.py tests/test_export.py
git commit -m "feat: allow sixteen execution riding days"
```

### Task 3: Select balanced lodging boundaries and rebuild the corridor

**Files:**
- Modify: `config/inland-execution-route.json`
- Modify: `config/inland-execution-poi-resolutions.json`
- Modify: `config/inland-itinerary.json`
- Modify: `route_planner/config.py`
- Modify: `tests/test_execution_itinerary.py`

**Interfaces:**
- Consumes: the fixed Day 7 start coordinate, the fixed HKUST(GZ) endpoint, live/cached AMap geocoding and electrobike candidates, and hotel evidence pages.
- Produces: ten contiguous Day 7–16 segments and nine Day 7–15 hotel endpoints.

- [ ] **Step 1: Establish cumulative target bands**

Measure candidates from the fixed Day 7 start against these cumulative targets: 95, 190, 285, 380, 475, 570, 665, 760, and 855 km. Each accepted adjacent leg must be ≤ 100 km; the remaining final leg must be 15–35 km. If a target lacks an acceptable hotel, the leg may drop to the 80–100 km band but never exceed 100 km.

- [ ] **Step 2: Search hotel POIs inside each target band**

For each cumulative target, search AMap along the existing 江西—粤东北—广州 corridor for hotels whose cycling-route distance falls within the band. For the ninth hotel, search 南沙/番禺 locations that leave 15–35 km to HKUST(GZ). Prefer high-rated local four-star/boutique hotels, 亚朵, or 维也纳国际; reject 汉庭 and 7 天.

- [ ] **Step 3: Verify lodging evidence before selecting a boundary**

For every selected Day 7–15 hotel, record one direct HTTPS hotel or map detail URL. Mark laundry `confirmed` only when the page explicitly lists a laundry room; otherwise use `call_required`. Reject hotels with recent cleanliness problems or a material route detour.

- [ ] **Step 4: Resolve and pin exact AMap POIs**

Update waypoint `display_name`, `city`, and `query` values, then run:

```bash
python3 scripts/resolve_pois.py \
  --config config/inland-execution-route.json \
  --env .env.local \
  --output /tmp/inland-execution-day16-resolutions.json \
  --cache-dir .cache/amap
```

Copy only the reviewed Day 7–15 POI blocks into `config/inland-execution-poi-resolutions.json`, retaining exact POI IDs, coordinates, addresses, and selection provenance.

- [ ] **Step 5: Replace only the Day 7–16 corridor entries**

Keep every waypoint through 鹰潭枫丹白露酒店 unchanged. Replace subsequent hotel waypoints, append the final pre-arrival hotel, and retain HKUST(GZ) as the final waypoint. Update `_INLAND_EXECUTION_CORRIDOR` to the same ordered display names.

- [ ] **Step 6: Assign one direct segment per day**

Create one `SegmentRule` for each adjacent Day 7–16 pair, with `day` values 7 through 16. Keep `anchor_queries` empty unless a hard-risk fix has exact public evidence; set every Day 7–16 itinerary `key_waypoints` to `[]`.

- [ ] **Step 7: Generate the candidate route**

Run:

```bash
python3 scripts/generate_route.py \
  --config config/inland-execution-route.json \
  --resolutions config/inland-execution-poi-resolutions.json \
  --env .env.local \
  --cache-dir .cache/amap \
  --output-dir web/data \
  --profile execution

python3 scripts/export_itinerary.py \
  --config config/inland-itinerary.json \
  --manifest web/data/inland-execution-route-manifest.json \
  --geojson web/data/inland-execution-route.geojson \
  --output web/data/inland-itinerary.json
```

- [ ] **Step 8: Inspect exact distances and iterate adjacent boundaries**

Run:

```bash
jq -r '.days[] | select(.day >= 7) | [.day,.date,.distance_m,.duration_s,.to_name] | @tsv' \
  web/data/inland-itinerary.json
```

If any Day 7–15 leg is over 100,000 m, move the shared endpoint back toward the previous night's hotel and regenerate both adjacent legs (do not widen the cap). If Day 16 is outside 15–35 km, replace only the Day 15 hotel. Never add a detour anchor to manufacture distance.

- [ ] **Step 9: Run itinerary tests and verify GREEN**

Run: `python3 -m unittest tests.test_config tests.test_execution_itinerary -v`

- [ ] **Step 10: Commit the balanced route configuration**

```bash
git add config/inland-execution-route.json config/inland-execution-poi-resolutions.json \
  config/inland-itinerary.json route_planner/config.py tests/test_execution_itinerary.py
git commit -m "feat: balance day seven through day sixteen"
```

### Task 4: Publish Day 1–16 map data and copy

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
- Modify: `tests/test_day_card_model.py`
- Modify: `tests/test_route_profile.py`
- Modify: `tests/test_web_contract.py`

**Interfaces:**
- Consumes: the audited Day 7–16 route and itinerary configuration.
- Produces: deployable Day 1–16 static map data, daily cards, totals, and cache-busted assets.

- [ ] **Step 1: Update public labels and summary copy**

Change execution copy from Day 1–15 to Day 1–16. State that Day 7–15 are 95–102 km and Day 16 is a short arrival day; update README totals from generated values rather than estimates.

- [ ] **Step 2: Bump route-data cache versions**

Use cache version `20260819-2` for `app.mjs`, `route-profile.mjs`, and `data/inland-itinerary.json`. Keep unchanged style/model module versions unchanged.

- [ ] **Step 3: Run focused web tests and syntax checks**

Run:

```bash
python3 -m unittest tests.test_day_card_model tests.test_route_profile tests.test_web_contract -v
node --check web/app.mjs
node --check web/map-coordinates.mjs
```

- [ ] **Step 4: Commit the publication artifacts**

```bash
git add README.md web route_planner/export.py tests/test_day_card_model.py \
  tests/test_route_profile.py tests/test_web_contract.py tests/test_inland_route.py tests/test_export.py
git commit -m "feat: publish sixteen-day execution map"
```

### Task 5: Audit, visually verify, and push

**Files:**
- Verify all modified and generated files.

**Interfaces:**
- Consumes: the complete Day 7–16 implementation.
- Produces: a clean, audited `main` branch synchronized with `origin/main`.

- [ ] **Step 1: Run the complete offline suite**

Run the full module list documented in `README.md`, excluding only `AmapLiveSmokeTest`. Expected result: zero failures.

- [ ] **Step 2: Run strict execution audit and hygiene checks**

```bash
python3 scripts/audit_route.py \
  --config config/inland-execution-route.json \
  --data-dir web/data \
  --env .env.local \
  --profile execution \
  --strict
node --check web/app.mjs
node --check web/map-coordinates.mjs
git diff --check
```

- [ ] **Step 3: Verify exact acceptance metrics**

Confirm Day 7–15 are each 95–102 km, at least five are at or below 100 km, Day 16 is 15–35 km on 2026-08-29, all Day 7–16 `key_waypoints` are empty, and every Day 7–15 lodging has evidence plus a laundry status.

- [ ] **Step 4: Verify the page in desktop and mobile viewports**

Open the local map, confirm 16 visible day cards, select Day 16 and verify only its route is emphasized, confirm AMap tiles and route geometry align, and test a 390×844 viewport for zero horizontal overflow with an independently scrolling itinerary panel.

- [ ] **Step 5: Commit remaining verification fixes and push**

Commit only if verification required a code/data correction. Push `main` normally, then confirm `git status --short --branch` is clean and `git rev-parse HEAD` equals `git rev-parse origin/main`; never force-push.

