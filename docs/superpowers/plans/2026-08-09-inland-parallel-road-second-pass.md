# Inland Parallel-Road Second Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the longest or highest-risk national-road exposure on the inland route with verified city, tourism, provincial, county, or township roads whenever the replacement materially lowers risk.

**Architecture:** Keep the published route manifest as the immutable baseline and add a small reroute-probe subsystem that evaluates explicit anchor sets against it. Live AMap calls write a deterministic comparison report first; only reviewed winners are copied into `config/inland-route.json` and regenerated into the public inland artifacts.

**Tech Stack:** Python 3 standard library, dataclasses, unittest, existing AMap Web Service client/cache, static GeoJSON/JSON/Markdown artifacts, vanilla JavaScript/Leaflet.

## Global Constraints

- The full-route detour ratio must remain at or below `1.15`; this limit applies route-wide rather than independently to every segment.
- At most 15 riding days are allowed, with no API subleg above 80 km and no planned riding day above 6 hours.
- P0 means at least 20 km of national road or a hard risk such as freight traffic, port access, expressway access, long bridge, long tunnel, or missing safe cycling space.
- A replacement must not introduce hard/freight exposure, isolated mountain roads, weak supply coverage, or unverified continuity merely to reduce a road number.
- Unknown road classification is not proof of safety; an increase of unknown distance must remain visible for manual review.
- AMap responses must use the existing ignored cache and the API key must remain only in `.env.local`.
- P0 probes run first, then the near-corridor 翁金线 scenic candidate, then P1; P2 connectors under 5 km are skipped unless evidence reveals a hard risk.
- Government or transport-department evidence is recorded for road condition and continuity, while the AMap route provides geometry and step-level road names.

---

### Task 1: Reroute probe definitions and deterministic safety comparison

**Files:**
- Create: `route_planner/reroutes.py`
- Create: `config/inland-reroute-probes.json`
- Create: `tests/test_reroutes.py`

**Interfaces:**
- Consumes: `PlannedSegment`, `SegmentRule`, and `candidate_metrics()` from the existing planner.
- Produces: `ProbeDefinition`, `ProbeCandidate`, `CandidateComparison`, `load_probe_definitions(path, valid_segment_ids)`, and `compare_candidate(current, proposed, full_baseline_m, other_selected_m, max_detour_ratio)`.

- [ ] **Step 1: Write failing schema and comparison tests**

```python
def _segment(*, segment_id="start-to-end", national_m=0, unknown_m=0, freight_m=0, hard_m=0, distance_m=80_000, baseline_m=80_000):
    start = Waypoint("start", "起点", "测试市", "起点", Coordinate(120.0, 30.0))
    end = Waypoint("end", "终点", "测试市", "终点", Coordinate(120.5, 30.5))
    steps = []
    if national_m:
        steps.append(RouteStep("沿G105骑行", "G105", national_m, (start.coordinate, end.coordinate), RoadClass.NATIONAL))
    if unknown_m:
        steps.append(RouteStep("沿未分类道路骑行", "未分类道路", unknown_m, (start.coordinate, end.coordinate), RoadClass.UNKNOWN))
    if freight_m:
        steps.append(RouteStep("沿物流大道骑行", "物流大道", freight_m, (start.coordinate, end.coordinate), RoadClass.CITY, frozenset({"freight"})))
    if hard_m:
        steps.append(RouteStep("沿快速路骑行", "城市快速路", hard_m, (start.coordinate, end.coordinate), RoadClass.CITY, frozenset({"hard"})))
    classified_m = national_m + unknown_m + freight_m + hard_m
    if classified_m < distance_m:
        steps.append(RouteStep("沿城市道路骑行", "城市道路", distance_m - classified_m, (start.coordinate, end.coordinate), RoadClass.CITY))
    selected = CandidateRoute(0, distance_m, 18_000, tuple(steps))
    return PlannedSegment(segment_id, start, end, SegmentRule(segment_id), baseline_m, selected, distance_m / baseline_m, (distance_m,), subleg_durations_s=(18_000,))

class RerouteTests(unittest.TestCase):
    def test_loads_p0_probe_with_evidence_and_named_anchor_sets(self):
        config = load_route_config(Path("config/inland-route.json"))
        probes = load_probe_definitions(Path("config/inland-reroute-probes.json"), set(config.segment_rules))
        probe = next(item for item in probes if item.segment_id == "main-19-to-main-20")
        self.assertEqual(probe.priority, "P0")
        self.assertTrue(probe.evidence_urls)
        self.assertTrue(all(candidate.anchor_queries for candidate in probe.candidates))

    def test_rejects_candidate_with_hard_or_freight_exposure(self):
        result = compare_candidate(
            current=_segment(national_m=40_000, distance_m=90_000),
            proposed=_segment(national_m=0, freight_m=500, distance_m=95_000),
            full_baseline_m=1_680_000,
            other_selected_m=1_720_000,
            max_detour_ratio=1.15,
        )
        self.assertEqual(result.decision, "rejected")
        self.assertIn("freight", result.reasons)

    def test_accepts_large_national_reduction_within_route_wide_budget(self):
        result = compare_candidate(
            current=_segment(national_m=40_000, distance_m=90_000),
            proposed=_segment(national_m=4_000, distance_m=105_000),
            full_baseline_m=1_680_000,
            other_selected_m=1_720_000,
            max_detour_ratio=1.15,
        )
        self.assertEqual(result.decision, "candidate")
        self.assertEqual(result.national_reduction_m, 36_000)

    def test_marks_unknown_substitution_for_manual_review(self):
        result = compare_candidate(
            current=_segment(national_m=30_000, unknown_m=1_000, distance_m=80_000),
            proposed=_segment(national_m=2_000, unknown_m=20_000, distance_m=90_000),
            full_baseline_m=1_680_000,
            other_selected_m=1_720_000,
            max_detour_ratio=1.15,
        )
        self.assertEqual(result.decision, "manual_review")
        self.assertIn("unknown_increase", result.reasons)
```

- [ ] **Step 2: Run the focused test and verify failure**

Run: `python3 -m unittest tests.test_reroutes -v`

Expected: FAIL because `route_planner.reroutes` does not exist.

- [ ] **Step 3: Implement immutable probe types, strict JSON loading, and comparison policy**

```python
@dataclass(frozen=True)
class ProbeCandidate:
    candidate_id: str
    anchor_queries: tuple[str, ...]
    road_hint: str

@dataclass(frozen=True)
class ProbeDefinition:
    segment_id: str
    priority: str
    evidence_urls: tuple[str, ...]
    candidates: tuple[ProbeCandidate, ...]
    scenic: bool = False

@dataclass(frozen=True)
class CandidateComparison:
    decision: str
    reasons: tuple[str, ...]
    national_reduction_m: int
    distance_delta_m: int
    projected_route_detour_ratio: float

def compare_candidate(current, proposed, full_baseline_m, other_selected_m, max_detour_ratio):
    old = candidate_metrics(current.selected)
    new = candidate_metrics(proposed.selected)
    projected = (other_selected_m + proposed.selected.distance_m) / full_baseline_m
    if new.hard_risk_m:
        return _comparison("rejected", ("hard",), old, new, current, proposed, projected)
    if new.freight_risk_m:
        return _comparison("rejected", ("freight",), old, new, current, proposed, projected)
    if projected > max_detour_ratio:
        return _comparison("rejected", ("route_detour_over_15_percent",), old, new, current, proposed, projected)
    if new.national_m >= old.national_m:
        return _comparison("rejected", ("national_not_reduced",), old, new, current, proposed, projected)
    if new.unknown_m - old.unknown_m > 5_000:
        return _comparison("manual_review", ("unknown_increase",), old, new, current, proposed, projected)
    return _comparison("candidate", (), old, new, current, proposed, projected)
```

The loader must reject duplicate candidate IDs, priorities outside `P0/P1/P2/SCENIC`, empty evidence lists for P0, empty anchor sets, and segment IDs absent from the supplied `valid_segment_ids` set.

- [ ] **Step 4: Seed the tracked probe registry**

Add these exact first-pass corridors to `config/inland-reroute-probes.json`:

```json
{
  "route_id": "inland-main",
  "probes": [
    {
      "segment_id": "main-19-to-main-20",
      "priority": "P0",
      "evidence_urls": [
        "https://www.ganzhou.gov.cn/gzszf/c100022/202606/f2db2e4d22544ec9bba7cb01c7403dfd.shtml",
        "https://glj.ganzhou.gov.cn/c101280/202203/67b9f0a9ad914e2bb99ae0d4b2bae965.shtml"
      ],
      "candidates": [
        {"candidate_id": "xinfeng-local-east", "anchor_queries": ["信丰县大塘埠镇", "信丰县小江镇", "龙南市里仁镇"], "road_hint": "S316/S317 与城镇道路组合"}
      ]
    },
    {
      "segment_id": "main-14-to-main-15",
      "priority": "P0",
      "evidence_urls": ["https://www.jxfz.gov.cn/art/2026/6/30/art_14_4458067.html"],
      "candidates": [
        {"candidate_id": "fuhe-towns", "anchor_queries": ["南丰县琴城镇", "南丰县太和镇", "广昌县甘竹镇"], "road_hint": "抚河沿线城镇及县乡道路"}
      ]
    },
    {
      "segment_id": "main-22-to-main-23",
      "priority": "P0",
      "evidence_urls": ["https://www.heyuan.gov.cn/zwgk/zdlyxx/zdjsxm/content/post_453605.html"],
      "candidates": [
        {"candidate_id": "s229-tourism-corridor", "anchor_queries": ["和平县礼士镇", "东源县船塘镇", "东源县漳溪畲族乡", "东源县骆湖镇"], "road_hint": "S229 旅游与城镇走廊"}
      ]
    },
    {
      "segment_id": "main-11-to-main-12",
      "priority": "P0",
      "evidence_urls": ["https://www.eco.gov.cn/news_info/40343.html"],
      "candidates": [
        {"candidate_id": "yiyang-guifeng", "anchor_queries": ["横峰县", "弋阳县龟峰景区", "贵溪市罗河镇"], "road_hint": "弋阳龟峰旅游道路与城镇道路"}
      ]
    },
    {
      "segment_id": "main-21-to-main-22",
      "priority": "P0",
      "evidence_urls": [
        "https://www.heping.gov.cn/xwzx/bmdt/content/post_702159.html?jump=false",
        "https://www.heping.gov.cn/zwgk/zdlyxxgk/zdjsxmxxgk/content/post_599721.html"
      ],
      "candidates": [
        {"candidate_id": "heping-green-corridor", "anchor_queries": ["和平县上陵镇", "和平县合水镇"], "road_hint": "G238 绿美公路；用于比较实际风险而非机械避号"}
      ]
    },
    {
      "segment_id": "main-02-to-main-03",
      "priority": "SCENIC",
      "scenic": true,
      "evidence_urls": ["https://www.haining.gov.cn/art/2024/7/7/art_1229519873_59045333.html"],
      "candidates": [
        {"candidate_id": "wengjin-ganpu", "anchor_queries": ["海盐县澉浦镇"], "road_hint": "翁金线澉浦绿道"}
      ]
    },
    {
      "segment_id": "main-03-to-main-04",
      "priority": "SCENIC",
      "scenic": true,
      "evidence_urls": ["https://www.haining.gov.cn/art/2024/7/7/art_1229519873_59045333.html"],
      "candidates": [
        {"candidate_id": "wengjin-yanguan", "anchor_queries": ["海宁市盐官旅游度假区"], "road_hint": "翁金线盐官段"}
      ]
    },
    {
      "segment_id": "main-17-to-main-18",
      "priority": "P1",
      "evidence_urls": [],
      "candidates": [
        {"candidate_id": "yudu-luoaok-jiangkou", "anchor_queries": ["于都县罗坳镇", "赣县区江口镇"], "road_hint": "沿镇区道路复核 G238 平行选择"}
      ]
    },
    {
      "segment_id": "main-06-to-main-07",
      "priority": "P1",
      "evidence_urls": [],
      "candidates": [
        {"candidate_id": "fuchunjiang-qiantan-xiaya", "anchor_queries": ["桐庐县富春江镇", "建德市乾潭镇", "建德市下涯镇"], "road_hint": "富春江沿线城镇道路复核"}
      ]
    },
    {
      "segment_id": "main-07-to-main-08",
      "priority": "P1",
      "evidence_urls": [],
      "candidates": [
        {"candidate_id": "datong-xikou", "anchor_queries": ["建德市大同镇", "龙游县溪口镇"], "road_hint": "县乡道路候选；重点排除偏僻山路"}
      ]
    },
    {
      "segment_id": "main-16-to-main-17",
      "priority": "P1",
      "evidence_urls": [],
      "candidates": [
        {"candidate_id": "laicun-yinkeng", "anchor_queries": ["宁都县赖村镇", "于都县银坑镇"], "road_hint": "城镇补给走廊候选"}
      ]
    }
  ]
}
```

The two scenic entries are excluded from the P0 run and evaluated together in Task 3, so one half cannot be adopted while the combined corridor is over budget or less safe.

- [ ] **Step 5: Run tests and commit**

Run: `python3 -m unittest tests.test_reroutes tests.test_config tests.test_roads -v`

Expected: PASS.

```bash
git add route_planner/reroutes.py config/inland-reroute-probes.json tests/test_reroutes.py
git commit -m "feat: define risk-weighted reroute probes"
```

---

### Task 2: Quota-efficient live probe CLI and auditable comparison report

**Files:**
- Create: `scripts/probe_reroutes.py`
- Create: `tests/test_probe_reroutes.py`

**Interfaces:**
- Consumes: `load_resolved_config()`, `RoutePlanner.plan_segment()`, the current `inland-route-manifest.json`, and Task 1 probe definitions.
- Produces: `ordered_probes(...)`, `evaluate_proposed_candidate(...)`, a live `plan_probe(...)` wrapper, and a JSON report at ignored path `cache/reports/inland-reroute-probes.json`.

- [ ] **Step 1: Write failing tests for priority order, cache-safe output, and route-wide comparison**

```python
from tests.test_reroutes import _segment

def _probe(priority):
    return ProbeDefinition(
        "start-to-end",
        priority,
        ("https://example.gov.cn/road",),
        (ProbeCandidate(f"candidate-{priority.lower()}", ("测试镇",), "测试道路"),),
        scenic=priority == "SCENIC",
    )

class ProbeRunnerTests(unittest.TestCase):
    def test_p0_definitions_run_before_scenic_and_p1(self):
        ordered = ordered_probes((_probe("P1"), _probe("SCENIC"), _probe("P0")))
        self.assertEqual([item.priority for item in ordered], ["P0", "SCENIC", "P1"])

    def test_evaluation_uses_other_published_segments_for_route_budget(self):
        definition = _probe("P0")
        report = evaluate_proposed_candidate(
            definition=definition,
            candidate=definition.candidates[0],
            current=_segment(distance_m=80_000, national_m=30_000),
            proposed=_segment(distance_m=90_000, national_m=0),
            published_segments=(
                _segment(distance_m=80_000, national_m=30_000),
                _segment(segment_id="other-segment", distance_m=1_600_000, baseline_m=1_600_000, national_m=0),
            ),
            max_detour_ratio=1.15,
        )
        self.assertLessEqual(report["projected_route_detour_ratio"], 1.15)
        self.assertEqual(report["decision"], "candidate")

    def test_report_contains_named_roads_and_before_after_metrics(self):
        definition = _probe("P0")
        report = evaluate_proposed_candidate(
            definition=definition,
            candidate=definition.candidates[0],
            current=_segment(national_m=20_000),
            proposed=_segment(national_m=1_000),
            published_segments=(_segment(national_m=20_000),),
            max_detour_ratio=1.15,
        )
        self.assertIn("road_names", report["proposed"])
        self.assertIn("national_m", report["current"])
        self.assertIn("unknown_m", report["proposed"])
        self.assertIn("distance_delta_m", report)
```

- [ ] **Step 2: Run the test and verify failure**

Run: `python3 -m unittest tests.test_probe_reroutes -v`

Expected: FAIL because `scripts.probe_reroutes` does not exist.

- [ ] **Step 3: Implement the live runner without automatic publication**

```python
def plan_probe(planner, definition, candidate, current, start, end, published_segments, max_detour_ratio):
    proposed_rule = replace(
        current.rule,
        anchor_queries=candidate.anchor_queries,
        parallel_road_available=False,
        allowed_national_m=0,
        national_exception_reason="",
    )
    proposed = planner.plan_segment(start, end, proposed_rule)
    full_baseline_m = sum(item.baseline_distance_m for item in published_segments)
    other_selected_m = sum(
        item.selected.distance_m for item in published_segments
        if item.segment_id != current.segment_id
    )
    return evaluate_proposed_candidate(
        definition, candidate, current, proposed, published_segments, max_detour_ratio
    )
```

`evaluate_proposed_candidate()` performs the route-wide totals shown above and returns the complete JSON-safe report; `plan_probe()` is the only function that calls AMap.

CLI contract:

```bash
python3 scripts/probe_reroutes.py \
  --config config/inland-route.json \
  --probes config/inland-reroute-probes.json \
  --resolutions config/inland-poi-resolutions.json \
  --manifest web/data/inland-route-manifest.json \
  --env .env.local \
  --cache-dir cache \
  --report cache/reports/inland-reroute-probes.json \
  --priority P0
```

The command must process P0 in descending current national-road distance, write the report after every completed candidate, retain earlier results if a later request hits quota, print no API key or response body, and never change `config/` or `web/data/`.

- [ ] **Step 4: Verify live reports use the already ignored cache tree and run tests**

Assert `git check-ignore cache/reports/inland-reroute-probes.json` prints that path, then run:

Run: `python3 -m unittest tests.test_probe_reroutes tests.test_reroutes tests.test_amap.AmapClientTests -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/probe_reroutes.py tests/test_probe_reroutes.py
git commit -m "feat: add cached reroute comparison runner"
```

---

### Task 3: Run P0, 翁金线, and P1 probes, review evidence, and adopt winners

**Files:**
- Modify: `config/inland-reroute-probes.json`
- Modify: `config/inland-route.json`
- Create: `web/data/inland-reroute-decisions.json`
- Create: `tests/test_inland_reroute_decisions.py`

**Interfaces:**
- Consumes: the ignored live report from Task 2 plus official road evidence.
- Produces: reviewed `adopted`, `rejected`, or `manual_review` decisions and updated anchor rules only for adopted candidates.

- [ ] **Step 1: After the daily quota reset, run only P0 probes**

Run the exact CLI command from Task 2 with `--priority P0`.

Expected: one result for every configured P0 candidate, or a partial durable report ending with an explicit quota error. Do not rerun completed cached candidates.

- [ ] **Step 2: Inspect every result against the actual objective**

For each P0 segment, compare:

```text
current/proposed national_m
current/proposed hard_risk_m and freight_risk_m
current/proposed unknown_m
distance_delta_m and projected_route_detour_ratio
subleg distances
proposed named roads
government evidence on road standard, construction, freight, tourism, and continuity
```

Special evidence decisions that must be recorded:

- 信丰→龙南: G105 has dense through freight and an Aug 2026 safety-upgrade project; a verified parallel route wins even with a moderate detour. If no safe parallel wins, retain only with a daylight/manual-navigation warning.
- 南城→广昌: the 28.472 km 白沙坪→田西村 G206 reconstruction opened in June 2026; do not replace it with an isolated mountain road unless the alternative is continuous and demonstrably safer.
- 定南→和平: G238 上陵段 is a completed 57.2 km green-road corridor; compare traffic and cycling space, not merely the national-road label.
- 和平→河源: S229 礼士/船塘/漳溪/骆湖 is a documented continuous provincial-road candidate with tourism/service-facility planning.
- 上饶→鹰潭: 龟峰 is useful only if the route avoids sustained G320 without introducing remote or over-budget roads.

- [ ] **Step 3: Write a failing decision-contract test**

```python
def load_probe_json():
    return json.loads(Path("config/inland-reroute-probes.json").read_text(encoding="utf-8"))["probes"]

def load_decisions():
    return json.loads(Path("web/data/inland-reroute-decisions.json").read_text(encoding="utf-8"))

class InlandRerouteDecisionTests(unittest.TestCase):
    def test_every_p0_and_p1_segment_has_a_reviewed_decision(self):
        data = load_decisions()
        required = {
            item["segment_id"]
            for item in load_probe_json()
            if item["priority"] in {"P0", "P1"}
        }
        decisions = {item["segment_id"]: item for item in data["decisions"]}
        self.assertEqual(set(decisions), required)
        self.assertTrue(all(item["status"] in {"adopted", "rejected", "manual_review"} for item in decisions.values()))
        self.assertTrue(all(item["decision_reason"] for item in decisions.values()))
        self.assertTrue(all("current" in item and "proposed" in item for item in decisions.values()))

    def test_adopted_decisions_match_route_config_anchors(self):
        config = load_route_config(Path("config/inland-route.json"))
        for item in load_decisions()["decisions"]:
            if item["status"] == "adopted":
                self.assertEqual(
                    list(config.segment_rules[item["segment_id"]].anchor_queries),
                    item["proposed"]["anchor_queries"],
                )
```

- [ ] **Step 4: Review the 翁金线 scenic corridor with the two tracked scenic probes**

Run:

```bash
python3 scripts/probe_reroutes.py \
  --config config/inland-route.json \
  --probes config/inland-reroute-probes.json \
  --resolutions config/inland-poi-resolutions.json \
  --manifest web/data/inland-route-manifest.json \
  --env .env.local \
  --cache-dir cache \
  --report cache/reports/inland-reroute-probes.json \
  --priority SCENIC
```

Adopt only if the combined corridor remains near the existing line, avoids new freight/hard risks, and the total projected detour remains at or below 1.15. Record the outcome in a separate `scenic_decisions` array; it does not satisfy any missing P0 decision.

- [ ] **Step 5: Run the four P1 probes after P0 and scenic decisions are available**

Run the same command with `--priority P1`. P1 probes may use the route-distance budget left after provisional P0/scenic winners, but cannot displace a P0 safety improvement merely to save distance. Require a decision record for every configured P1 segment even when the result is rejection or manual review.

- [ ] **Step 6: Apply only reviewed winners and update measured allowances**

For each adopted result, copy measured data with this exact transformation while preparing the reviewed config edit:

```python
rule = config_payload["segment_rules"][result["segment_id"]]
rule["anchor_queries"] = result["proposed"]["anchor_queries"]
rule["allowed_national_m"] = result["proposed"]["national_m"]
rule["national_exception_reason"] = decision["decision_reason"]
```

`decision_reason` must contain the measured before/after national-road distance, projected full-route detour ratio, hard/freight result, evidence conclusion, and remaining manual-review condition. For rejected/manual decisions, leave the current config anchors unchanged and state the concrete reason in `inland-reroute-decisions.json`.

- [ ] **Step 7: Run tests and commit decisions**

Run: `python3 -m unittest tests.test_inland_reroute_decisions tests.test_inland_config tests.test_config -v`

Expected: PASS.

```bash
git add config/inland-reroute-probes.json config/inland-route.json web/data/inland-reroute-decisions.json tests/test_inland_reroute_decisions.py
git commit -m "data: adopt reviewed inland safety reroutes"
```

---

### Task 4: Regenerate selected geometry, expose decisions, and complete the safety audit

**Files:**
- Modify: `route_planner/models.py`
- Modify: `route_planner/config.py`
- Modify: `route_planner/manifest.py`
- Modify: `route_planner/export.py`
- Modify: `web/app.mjs`
- Modify: `web/data/inland-route.geojson`
- Modify: `web/data/inland-route-manifest.json`
- Modify: `web/data/inland-summary.json`
- Modify: `web/data/inland-review.md`
- Modify: `README.md`
- Modify: `tests/test_export.py`
- Modify: `tests/test_audit.py`
- Modify: `tests/test_web_contract.py`

**Interfaces:**
- Consumes: Task 3 adopted decisions and changed route rules.
- Produces: regenerated map geometry with `reroute_status`/`reroute_reason`, compact decision labels, and final route-wide verification evidence.

- [ ] **Step 1: Write failing export/manifest/web tests for visible decisions**

```python
class RerouteExportTests(unittest.TestCase):
    def test_geojson_exposes_segment_reroute_decision(self):
        original = _segment()
        segment = replace(
            original,
            rule=replace(original.rule, reroute_status="adopted", reroute_reason="国道减少 30 km"),
        )
        properties = build_geojson([segment])["features"][0]["properties"]
        self.assertEqual(properties["reroute_status"], "adopted")
        self.assertEqual(properties["reroute_reason"], "国道减少 30 km")

class WebMapContractTests(unittest.TestCase):
    def test_map_renders_compact_reroute_badge(self):
        js = Path("web/app.mjs").read_text(encoding="utf-8")
        self.assertIn("reroute_status", js)
        self.assertIn("已绕行", js)
        self.assertIn("需人工复核", js)
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `python3 -m unittest tests.test_export tests.test_artifacts tests.test_web_contract -v`

Expected: FAIL because reroute decision fields are not exported or rendered.

- [ ] **Step 3: Add backward-compatible decision fields**

Extend `SegmentRule` with:

```python
reroute_status: str = "unreviewed"
reroute_reason: str = ""
```

The config loader accepts only `unreviewed`, `adopted`, `rejected`, or `manual_review`. The manifest serializer/deserializer preserves the fields with backward-compatible defaults. `_step_properties()` includes both fields for every road-step feature.

In `web/app.mjs`, append one short badge to segment metadata:

```javascript
const rerouteLabels = {
  adopted: "已绕行",
  rejected: "保留原线",
  manual_review: "需人工复核",
};
const rerouteLabel = rerouteLabels[first.reroute_status];
meta.textContent = `${formatDistance(sumDistance(entry.features))} · ${entry.features.length} 个道路步骤${rerouteLabel ? ` · ${rerouteLabel}` : ""}`;
```

- [ ] **Step 4: Regenerate the config-aligned route, then atomically republish**

Run a full config-aligned generation. Existing baselines and unchanged sublegs are read from the ignored cache; P0 and scenic candidate requests completed in Task 3 are also cached. A full pass is required because rejected/manual decision metadata changes the manifest rules even when geometry stays unchanged.

```bash
python3 scripts/generate_route.py \
  --config config/inland-route.json \
  --resolutions config/inland-poi-resolutions.json \
  --env .env.local \
  --output-dir web/data \
  --cache-dir cache \
  --profile inland
```

- [ ] **Step 5: Run the full deterministic verification suite**

Run:

```bash
python3 -m unittest \
  tests.test_amap.AmapClientTests \
  tests.test_artifacts \
  tests.test_audit \
  tests.test_config \
  tests.test_coordinates \
  tests.test_export \
  tests.test_inland_config \
  tests.test_inland_route \
  tests.test_inland_reroute_decisions \
  tests.test_planner \
  tests.test_probe_reroutes \
  tests.test_reroutes \
  tests.test_roads \
  tests.test_web_contract -v
python3 scripts/audit_route.py \
  --config config/inland-route.json \
  --env .env.local \
  --output-dir web/data \
  --profile inland \
  --strict
git diff --check
```

Expected: all tests PASS; strict audit exits 0; diff check exits 0.

- [ ] **Step 6: Perform requirement-by-requirement data audit**

Read `web/data/inland-summary.json`, `web/data/inland-reroute-decisions.json`, and `web/data/inland-review.md` and verify all of the following with exact values:

```text
main.detour_ratio <= 1.15
schedule.max_riding_days == 15
schedule.deadline_feasible == true, or the schedule remains intentionally hidden until the separate 15-day split is locked
no hard/freight step is published as automatic_checks_passed
every P0 segment has adopted/rejected/manual_review evidence
each adopted segment reduced national-road or hard-risk exposure
remaining national-road segments are listed by descending distance with a reason
UNKNOWN increases are explicitly marked for manual review
```

Do not claim the route is fully safe if road-level or on-the-day conditions remain unverified.

- [ ] **Step 7: Update README and commit the regenerated route**

Update the current-status paragraph with exact before/after national-road distance, overall detour ratio, adopted P0 count, and remaining manual-review count.

```bash
git add route_planner config web README.md tests
git commit -m "feat: publish lower-risk inland route revision"
git status --short --branch
```

Expected: branch `main` is clean after the commit.
