# Tongxiang Execution Itinerary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish a real AMap-backed Day 0–Day 15 execution map, correct Day 1 to Tongxiang through 叶新公路, and provide balanced daily stops with on-route laundry-capable hotels.

**Architecture:** Keep the reviewed legacy inland route intact and add a separate `inland-execution` route profile for the current trip. Generate its route geometry with the existing AMap planner, then merge an explicit itinerary contract into day-tagged GeoJSON and day-card JSON consumed by the Leaflet UI.

**Tech Stack:** Python 3.12, unittest, AMap electrobike API/cache, JSON, GeoJSON, GPX 1.1, Leaflet, ES modules, HTML/CSS, Git.

## Global Constraints

- Use only方案 A: target even daily distance, then snap to a suitable on-route hotel.
- Do not add distance to chase a hotel brand; every planned hotel must have laundry evidence or be visibly marked for confirmation.
- Day 1 must end at 桐乡万象汇振兴西路亚朵酒店 and use 叶新公路 as the principal corridor.
- Day 2 is a 0 km stay/work/preparation day in 桐乡.
- Day 3 is 桐乡 → 阿里巴巴西溪园区 → 杭州阿里巴巴西溪园区爱橙街亚朵 S 酒店, about 70.4 km.
- Day 15 ends at 香港科技大学（广州）.
- Keep API keys and generated caches out of Git.
- Commit to `main` and push without force to `git@github.com:wfnuser/from-sjtu-to-hkust-gz.git`.

## Planned Night Stops

| Day | Endpoint | Laundry evidence |
| --- | --- | --- |
| 3 | 杭州阿里巴巴西溪园区爱橙街亚朵 S 酒店 | 亚朵自助洗衣 |
| 4 | 杭州建德新安江风景区新安东路亚朵酒店 | 7×24 洗熨烘 |
| 5 | 常山东方广场酒店 | 洗衣房 |
| 6 | 维也纳酒店（上饶横峰古窑路店） | 洗衣房 |
| 7 | 维也纳国际酒店（抚州东站店） | 自助洗衣房 |
| 8 | 维也纳国际酒店（南丰桔都大道店） | 免费洗衣房、干衣机 |
| 9 | 汉庭酒店（赣州宁都州城文化街店） | 洗衣房 |
| 10 | 维也纳酒店（于都高铁站店） | 自助洗衣 |
| 11 | 维也纳酒店（赣州信丰高铁西站店） | 洗衣房 |
| 12 | 维也纳酒店（河源和平店） | 自助洗衣房 |
| 13 | 亚朵酒店（河源越王大道店） | 亚朵自助洗衣 |
| 14 | 维也纳酒店（惠州博罗福田店） | 免费洗衣、干衣机 |

---

### Task 1: Lock the execution-route and itinerary contracts

**Files:**
- Create: `tests/test_execution_itinerary.py`
- Create: `config/inland-execution-route.json`
- Create: `config/inland-execution-poi-resolutions.json`
- Create: `config/inland-itinerary.json`
- Modify: `route_planner/config.py`

**Interfaces:**
- Consumes: `load_route_config(path: Path) -> RouteConfig`
- Produces: route ID `inland-execution`, ordered waypoints, segment rules with explicit `day`, and 16 itinerary day records.

- [ ] **Step 1: Write failing tests for fixed days and lodging**

```python
def test_fixed_execution_days(self):
    payload = json.loads(Path("config/inland-itinerary.json").read_text())
    self.assertEqual([day["day"] for day in payload["days"]], list(range(16)))
    self.assertEqual(payload["days"][1]["to_name"], "桐乡万象汇振兴西路亚朵酒店")
    self.assertIn("叶新公路", payload["days"][1]["key_waypoints"])
    self.assertEqual(payload["days"][2]["distance_m"], 0)
    self.assertEqual(payload["days"][3]["to_name"], "杭州阿里巴巴西溪园区爱橙街亚朵S酒店")
    self.assertTrue(all(day.get("lodging", {}).get("laundry") for day in payload["days"][3:15]))
```

- [ ] **Step 2: Run the focused test and verify it fails because the execution files do not exist**

Run: `python3 -m unittest tests.test_execution_itinerary -v`

- [ ] **Step 3: Add the exact execution waypoint corridor**

The route must preserve the Shanghai Day 0 check-ins, then use these day boundaries: 叶新公路东/西锚点、桐乡酒店、西溪园区、西溪亚朵 S、建德亚朵、常山东方广场、横峰维也纳、东乡维也纳、南丰维也纳、宁都汉庭、于都维也纳、信丰维也纳、和平维也纳、河源亚朵、博罗福田维也纳、港科大（广州）. Intermediate corridor points remain 桐庐、龙游、衢州、玉山、上饶、鹰潭、抚州、南城、广昌、赣州、龙南、定南、埔前、杨村、增城、番禺.

- [ ] **Step 4: Add selected GCJ-02 POI provenance and the exact Day 0–Day 15 itinerary JSON**

Every riding day lists ordered segment IDs; Day 2 lists an empty segment array and status `stay`. Each lodging object has `name`, `laundry`, `evidence_url`, and `booking_status: "candidate"`.

- [ ] **Step 5: Run the focused test and commit the contract**

Run: `python3 -m unittest tests.test_execution_itinerary -v`

Commit: `feat: define executable daily itinerary`

### Task 2: Generate and publish the AMap execution route

**Files:**
- Modify: `route_planner/artifacts.py`
- Modify: `scripts/generate_route.py`
- Create: `route_planner/itinerary.py`
- Create: `scripts/export_itinerary.py`
- Create: `web/data/inland-execution-route.geojson`
- Create: `web/data/inland-execution-summary.json`
- Create: `web/data/inland-execution-route-manifest.json`
- Create: `web/data/inland-itinerary.json`

**Interfaces:**
- Produces: `build_itinerary(day_config: dict, manifest: Sequence[PlannedSegment], geojson: dict) -> tuple[dict, dict]` returning day-card JSON and GeoJSON whose road features contain integer `day_id`.

- [ ] **Step 1: Add failing tests for day tagging, distance sums, and Day 2's empty route**

```python
def test_every_execution_segment_has_one_day(self):
    itinerary, geojson = build_itinerary(self.config, self.segments, self.geojson)
    self.assertEqual(set(itinerary["segment_days"]), {s.segment_id for s in self.segments})
    self.assertTrue(all(isinstance(f["properties"]["day_id"], int) for f in geojson["features"]))
    self.assertEqual(itinerary["days"][2]["distance_m"], 0)
```

- [ ] **Step 2: Extend fixed artifact paths with profile `execution` and verify the new test fails before implementation**

Run: `python3 -m unittest tests.test_execution_itinerary -v`

- [ ] **Step 3: Implement strict itinerary merging**

Reject missing, duplicate, or unordered segment IDs; derive each day's distance/duration from the manifest; set `remaining_distance_m` to the sum of Day 3–Day 15 and `average_riding_distance_m` to that total divided by 13.

- [ ] **Step 4: Generate all real AMap segments and publish the execution artifacts**

Run:

```bash
python3 scripts/generate_route.py \
  --config config/inland-execution-route.json \
  --resolutions config/inland-execution-poi-resolutions.json \
  --env .env.local --cache-dir .cache/amap \
  --output-dir web/data --profile execution
python3 scripts/export_itinerary.py \
  --config config/inland-itinerary.json \
  --manifest web/data/inland-execution-route-manifest.json \
  --geojson web/data/inland-execution-route.geojson \
  --output web/data/inland-itinerary.json
```

- [ ] **Step 5: Assert Day 3 is approximately 70.4 km and Day 4–Day 15 have real nonzero geometry, then commit**

Commit: `data: publish balanced execution route`

### Task 3: Render Day 0–Day 15 as the primary navigation

**Files:**
- Modify: `tests/test_route_profile.py`
- Modify: `tests/test_web_contract.py`
- Modify: `web/route-profile.mjs`
- Modify: `web/app.mjs`
- Modify: `web/index.html`
- Modify: `web/styles.css`

**Interfaces:**
- Consumes: `data/inland-itinerary.json` and GeoJSON `properties.day_id`
- Produces: `renderDayCards(itinerary)` and `fitDay(dayId)`.

- [ ] **Step 1: Add failing web contract tests**

The tests require `inlandExecution`, `renderDayCards`, `fitDay`, `properties.day_id`, exact Day 0–Day 15 card labels, independent sidebar scrolling, and an expandable road detail region.

- [ ] **Step 2: Run focused tests and verify failure**

Run: `python3 -m unittest tests.test_route_profile tests.test_web_contract -v`

- [ ] **Step 3: Switch the default inland page to execution artifacts and render only day cards in the primary list**

Each card shows status, endpoint pair, distance, duration, key waypoints, hotel, laundry, and risk note. Clicking calls `fitDay(dayId)` and visually emphasizes only that day's layers.

- [ ] **Step 4: Keep detailed roads inside the expanded day card and preserve the compact right-top legend**

Day 2 remains clickable but does not alter map bounds. Mobile sidebar height stays within the viewport and scrolls independently.

- [ ] **Step 5: Run focused tests and commit**

Commit: `feat: navigate the route by riding day`

### Task 4: Replace the obsolete Day 1 GPX and Markdown roadbook

**Files:**
- Create: `scripts/export_day_roadbook.py`
- Modify outside Git: `/Users/huangqinghao/Workspace/ClaudeSpace/Exports/SJTU-HKUSTGZ-Day1/day-01-shanghai-to-tongxiang.gpx`
- Modify outside Git: `/Users/huangqinghao/Workspace/ClaudeSpace/Exports/SJTU-HKUSTGZ-Day1/day-01-roadbook.md`
- Remove outside Git after replacement: `/Users/huangqinghao/Workspace/ClaudeSpace/Exports/SJTU-HKUSTGZ-Day1/day-01-shanghai-to-caojing.gpx`

**Interfaces:**
- Consumes: execution manifest plus Day 1 segment IDs.
- Produces: GPX 1.1 route/track and Chinese Markdown roadbook ending at the Tongxiang hotel.

- [ ] **Step 1: Add a failing exporter test**

Assert the GPX contains `叶新公路`, does not contain `漕泾`, and the final coordinate/name is the Tongxiang hotel.

- [ ] **Step 2: Implement `export_day(manifest, itinerary, day, output_dir)` using only published WGS84 route geometry**

- [ ] **Step 3: Generate Day 1 outside the repository and inspect both files**

- [ ] **Step 4: Delete only the obsolete generated Caojing GPX after the replacement files pass validation**

- [ ] **Step 5: Commit the reusable exporter**

Commit: `feat: export corrected daily roadbooks`

### Task 5: Verify and publish

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-08-15-tongxiang-day-itinerary-design.md`

- [ ] **Step 1: Document the execution profile, local server command, and roadbook export command**

- [ ] **Step 2: Run all automated checks**

```bash
python3 -m unittest discover -s tests -v
node --check web/app.mjs
node --check web/route-profile.mjs
python3 scripts/audit_route.py --geojson web/data/inland-execution-route.geojson --summary web/data/inland-execution-summary.json --strict
git diff --check
```

- [ ] **Step 3: Open the local page and verify Day 0–Day 15, Day 1叶新公路, Day 3西溪酒店, daily map zoom, and mobile scrolling**

- [ ] **Step 4: Commit remaining docs/data, push `main`, and verify `origin/main` equals `HEAD`**

