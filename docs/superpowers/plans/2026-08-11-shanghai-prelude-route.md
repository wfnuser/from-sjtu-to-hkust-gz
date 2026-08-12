# Shanghai Prelude Route Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prepend the four-stop Shanghai city route to the existing complete inland route without renumbering or replacing any post-SJTU segment.

**Architecture:** Keep the established `main-*` corridor immutable and add `pre-*` waypoints before it. Resolve the new POIs in the existing reviewed resolution artifact, then regenerate the same inland GeoJSON, summary, review, and manifest from cached AMap responses.

**Tech Stack:** Python 3 standard library, cached AMap Web Service responses, GeoJSON, Leaflet, unittest.

## Global Constraints

- Work on `main` as explicitly requested by the user.
- Do not expose or commit `.env.local` or the AMap API key.
- Preserve every existing `main-*` segment ID and reroute decision.
- The default page remains the single complete inland map.

---

### Task 1: Lock the complete corridor contract

**Files:**
- Modify: `tests/test_inland_config.py`
- Modify: `tests/test_web_contract.py`

**Interfaces:**
- Consumes: `load_route_config(Path("config/inland-route.json"))`
- Produces: acceptance assertions for the new start, SJTU junction, unchanged post-SJTU segment, and page heading.

- [ ] Add a failing test asserting the first five waypoint IDs are `pre-01`, `pre-02`, `pre-03`, `pre-04`, `main-01` and the last remains `main-27`.
- [ ] Add a failing artifact test asserting both `pre-04-to-main-01` and `main-01-to-main-02` are published.
- [ ] Run the focused tests and confirm they fail because the prelude is absent.

### Task 2: Add the prelude configuration and selected POIs

**Files:**
- Modify: `route_planner/config.py`
- Modify: `config/inland-route.json`
- Modify: `config/inland-poi-resolutions.json`
- Modify: `web/index.html`
- Modify: `README.md`

**Interfaces:**
- Consumes: manually confirmed AMap POI IDs and GCJ-02 coordinates.
- Produces: a fully resolved 31-waypoint inland config with 30 explicit segment rules.

- [ ] Change the inland-only start invariant while retaining the SJTU start invariant for coastal/sample routes.
- [ ] Prepend four `pre-*` waypoints and four segment rules.
- [ ] Prepend exactly one selected POI resolution for each new query.
- [ ] Update public route copy to describe the full start and retain SJTU as the symbolic junction.
- [ ] Run the focused tests and confirm they pass.

### Task 3: Regenerate and verify the single complete map

**Files:**
- Modify generated artifacts: `web/data/inland-route.geojson`, `web/data/inland-summary.json`, `web/data/inland-review.md`, `web/data/inland-route-manifest.json`

**Interfaces:**
- Consumes: `config/inland-route.json`, `config/inland-poi-resolutions.json`, ignored `.env.local`, and `cache/`.
- Produces: one complete published inland route containing 30 ordered segments.

- [ ] Record cache file count, run the inland generator, and record the count again.
- [ ] Assert the manifest begins with four `pre-*` segments and then the unchanged `main-01-to-main-02` segment.
- [ ] Run the full unit suite, strict route audit, JavaScript syntax checks, and `git diff --check`.
- [ ] Restart the existing port 8765 server, open the default inland page, and verify the complete map loads.
- [ ] Commit all reviewed changes on `main`.

