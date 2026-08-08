# Lightweight Map Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the road legend into a compact map overlay and make the information panel and map fill the visible screen without page overflow.

**Architecture:** Keep the existing static HTML, CSS, Leaflet code, and route data unchanged. Move only the legend markup into `.map-pane`; use CSS viewport sizing and nested overflow so the sidebar scrolls independently while the map stays fixed.

**Tech Stack:** Static HTML, native CSS, Leaflet 1.9.4, Python `unittest` contract tests

## Global Constraints

- The legend is always visible in the map's upper-right corner and has no disclosure control.
- Desktop uses two legend columns; narrow screens use a compact single column.
- The sidebar and map fill the visible screen with CSS `100dvh`; JavaScript does not measure or synchronize heights.
- Do not add dependencies or change route data, colors, labels, totals, or interactions.
- Preserve a usable stacked layout below 860 px without horizontal overflow.

---

### Task 1: Encode the layout contract

**Files:**
- Modify: `tests/test_web_contract.py`

**Interfaces:**
- Consumes: `web/index.html` and `web/styles.css` as public static artifacts.
- Produces: `WebMapContractTests.test_map_uses_compact_overlay_legend_and_nested_scrolling()`.

- [ ] **Step 1: Write the failing contract test**

```python
def test_map_uses_compact_overlay_legend_and_nested_scrolling(self):
    html = Path("web/index.html").read_text(encoding="utf-8")
    css = Path("web/styles.css").read_text(encoding="utf-8")

    self.assertIn('<section class="map-legend"', html)
    self.assertNotIn('<section class="panel legend"', html)
    self.assertIn("height: 100dvh", css)
    self.assertIn("overflow: hidden", css)
    self.assertIn("overflow-y: auto", css)
    self.assertIn("grid-template-columns: repeat(2, max-content)", css)
```

- [ ] **Step 2: Run the contract test and verify RED**

Run: `python3 -m unittest tests.test_web_contract.WebMapContractTests.test_map_uses_compact_overlay_legend_and_nested_scrolling -v`

Expected: FAIL because `map-legend` is absent from `web/index.html`.

- [ ] **Step 3: Commit the test only after the RED result is recorded**

```bash
git add tests/test_web_contract.py
git commit -m "test: specify compact map layout"
```

### Task 2: Move and restyle the legend

**Files:**
- Modify: `web/index.html`
- Modify: `web/styles.css`

**Interfaces:**
- Consumes: existing `.swatch` classes and the six existing legend labels.
- Produces: `.map-legend`, a non-interactive overlay inside `.map-pane`.

- [ ] **Step 1: Move the existing six legend items into the map pane**

Replace the sidebar's `<section class="panel legend">` with this element immediately after `#map`:

```html
<section class="map-legend" aria-label="道路图例">
  <ul>
    <li><span class="swatch cycleway"></span>骑行道</li>
    <li><span class="swatch county"></span>县道／旅游道路</li>
    <li><span class="swatch provincial"></span>省道</li>
    <li><span class="swatch national"></span>国道</li>
    <li><span class="swatch review"></span>需人工复核</li>
    <li><span class="swatch optional"></span>可选支线</li>
  </ul>
</section>
```

- [ ] **Step 2: Implement screen-height layout and nested scrolling**

Add or adjust these declarations while retaining existing visual tokens:

```css
html, body { height: 100%; }
body { overflow: hidden; }
.route-app { height: 100dvh; min-height: 0; }
.sidebar { height: 100dvh; min-height: 0; overflow-y: auto; overscroll-behavior: contain; }
.map-pane, #map { height: 100dvh; min-height: 0; }
```

- [ ] **Step 3: Add the lightweight overlay styling**

```css
.map-legend {
  position: absolute;
  top: 16px;
  right: 16px;
  z-index: 600;
  padding: 9px 11px;
  pointer-events: none;
  background: rgb(255 255 255 / 88%);
  border: 1px solid rgb(203 213 225 / 85%);
  border-radius: 8px;
  box-shadow: 0 4px 16px rgb(15 23 42 / 9%);
  backdrop-filter: blur(6px);
}
.map-legend ul {
  display: grid;
  grid-template-columns: repeat(2, max-content);
  gap: 7px 14px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.map-legend li { display: flex; align-items: center; gap: 7px; color: #4d5b70; font-size: .75rem; }
.map-legend .swatch { width: 18px; border-top-width: 3px; }
```

- [ ] **Step 4: Preserve a bounded mobile split**

At `max-width: 860px`, use `grid-template-rows: 42dvh 58dvh`, set the sidebar and map pane to those row heights, and keep sidebar overflow internal. At `max-width: 420px`, switch `.map-legend ul` to one column and reduce gap/padding.

- [ ] **Step 5: Run the focused and full deterministic tests**

Run: `python3 -m unittest tests.test_web_contract -v`

Expected: all web contract tests PASS.

Run: `python3 -m unittest tests.test_amap.AmapClientTests tests.test_artifacts tests.test_audit tests.test_config tests.test_coordinates tests.test_export tests.test_inland_config tests.test_inland_route tests.test_planner tests.test_roads tests.test_web_contract -v`

Expected: all deterministic tests PASS without making live AMap requests.

- [ ] **Step 6: Verify the rendered layout at desktop and narrow widths**

Serve `web/` locally, inspect 1440×900 and 390×844 viewports, and verify all five acceptance criteria in the design spec. Confirm that only the sidebar scrolls on desktop and that map dragging works beneath the non-interactive legend.

- [ ] **Step 7: Commit the implementation**

```bash
git add web/index.html web/styles.css
git commit -m "feat: lighten map legend and contain layout"
```
