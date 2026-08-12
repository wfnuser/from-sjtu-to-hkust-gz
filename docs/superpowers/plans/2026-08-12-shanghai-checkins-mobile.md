# Shanghai Check-ins and Mobile Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the three confirmed Shanghai check-ins to the complete inland route, publish regenerated route artifacts, and make the map usable on mobile screens.

**Architecture:** Extend the declarative inland waypoint corridor and the manually approved POI resolution file, then let the existing AMap-backed generator rebuild the full route. Keep responsive behavior isolated in CSS and protect both route continuity and mobile interaction through contract tests.

**Tech Stack:** Python 3.12, unittest, JSON route configuration, AMap electrobike API/cache, Leaflet, HTML/CSS/ES modules, Git.

## Global Constraints

- Preserve every existing inland waypoint from `main-01` through `main-27` and all reroute review artifacts.
- The first eight waypoints must be 阳曲路、交大附中本部、bilibili 国正中心、大连路地铁站、昌化路649号、京东中海中心、阿里虹桥、上海交通大学闵行校区.
- Publish only real AMap cycling polylines that pass the existing safety audit.
- Keep desktop layout unchanged above 860 pixels.
- Commit to `main` and push to `git@github.com:wfnuser/from-sjtu-to-hkust-gz.git`.

---

### Task 1: Lock the expanded Shanghai prelude contract

**Files:**
- Modify: `tests/test_inland_config.py`
- Modify: `route_planner/config.py`
- Modify: `config/inland-route.json`
- Modify: `config/inland-poi-resolutions.json`

**Interfaces:**
- Consumes: `load_route_config(Path) -> RouteConfig`
- Produces: a 34-waypoint corridor with 33 adjacent segment rules

- [ ] Add a failing test for the exact first eight waypoint names and 33 published segments.
- [ ] Run the focused test and verify it fails against the current five-point prefix.
- [ ] Add `pre-02` through `pre-04` for the three new POIs and renumber the existing prelude IDs without changing `main-*` IDs.
- [ ] Add confirmed AMap POI provenance and one segment rule per new adjacency.
- [ ] Run the focused test and verify it passes.

### Task 2: Regenerate and audit the complete route

**Files:**
- Modify: `web/data/inland-route-manifest.json`
- Modify: `web/data/inland-route.geojson`
- Modify: `web/data/inland-summary.json`
- Modify: `web/data/inland-review.md`

**Interfaces:**
- Consumes: the expanded inland route and confirmed POI resolutions
- Produces: 33 real-polyline inland segments ending at 香港科技大学（广州）

- [ ] Run `scripts/generate_route.py` with the inland profile and local AMap environment.
- [ ] Assert the first seven segment IDs, final segment ID, segment count, and first-day distance.
- [ ] Run `scripts/audit_route.py --strict` and stop if any hard or freight risk is published.

### Task 3: Make the map mobile-friendly

**Files:**
- Modify: `tests/test_web_contract.py`
- Modify: `web/styles.css`

**Interfaces:**
- Consumes: the existing `.route-app`, `.sidebar`, `.map-pane`, `.map-legend`, and route button classes
- Produces: map-first mobile layout with independent content scrolling and 44px touch targets

- [ ] Add failing CSS contract assertions for mobile map ordering, safe-area handling, and touch target height.
- [ ] Run the focused web contract test and verify it fails.
- [ ] Implement the mobile media rules while leaving the desktop grid unchanged.
- [ ] Run the focused test and verify it passes.

### Task 4: Verify, commit, and publish

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: the complete verified working tree
- Produces: a clean `main` commit pushed to the configured GitHub origin

- [ ] Update the README route prefix and mobile behavior note.
- [ ] Run the full Python suite, JavaScript syntax checks, strict route audit, and `git diff --check`.
- [ ] Open the local page at a mobile viewport and verify the map, first seven cards, and full-route continuation.
- [ ] Commit all verified changes on `main`.
- [ ] Configure `origin` as `git@github.com:wfnuser/from-sjtu-to-hkust-gz.git` and push `main` without force.
