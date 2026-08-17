# Day Route Highlight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Make a selected Day card highlight only that day's main-route geometry, dim the other days, and restore the full-route overview when the selected card is clicked again.

**Architecture:** Put the selection transition and route-style calculation in a small DOM-free module so they can be tested directly with Node. Keep Leaflet layer ownership in `web/app.mjs`: the app stores the selected Day ID, applies calculated styles to existing step layers, synchronizes card accessibility state, and chooses either day or main-route bounds.

**Tech Stack:** Browser-native JavaScript modules, Leaflet 1.9.4, CSS, Python `unittest` with Node subprocess tests.

## Global Constraints

- Clicking a Day selects it, highlights its route, dims other main-route days, and fits its bounds.
- Clicking a different Day switches the selection immediately.
- Clicking the selected Day clears the selection and restores the complete main-route bounds and styles.
- Day buttons expose selection with `aria-pressed`; pointer, touch, and keyboard activation use the same button handler.
- Optional branches, reroute comparison layers, review data, and popups remain unchanged.
- The selected route keeps its road-class color while using greater weight and opacity.
- Day 4 is `2026-08-18`; `start_date: 2026-08-14` derives Day 1–15 ISO dates through `2026-08-29`, and cards display them as `M月D日`.

---

### Task 1: Pure Day Selection and Style Rules

**Files:**
- Create: `web/day-selection.mjs`
- Create: `tests/test_day_selection.py`
- Modify: `web/day-card-model.mjs`
- Modify: `tests/test_day_card_model.py`

**Interfaces:**
- Consumes: a current selected Day ID (`number | null`), a clicked Day ID (`number`), a GeoJSON feature, and the feature's base Leaflet path style.
- Produces: `nextSelectedDayId(currentDayId, clickedDayId) -> number | null` and `routeStyleForSelectedDay(feature, selectedDayId, baseStyle) -> object`.

- [x] **Step 1: Write failing transition tests**

Create `tests/test_day_selection.py` with Node-backed assertions that:

```python
self.assertEqual(run_selection(None, 4), 4)
self.assertEqual(run_selection(4, 5), 5)
self.assertIsNone(run_selection(4, 4))
```

Also assert that no selection returns the base style unchanged, a Day 4 feature selected on Day 4 has opacity `1` and weight at least `6`, a Day 5 feature selected on Day 4 has opacity no greater than `0.2`, and an optional-branch feature returns the base style unchanged.

Extend `tests/test_day_card_model.py` with a Day 4 fixture containing `date: "2026-08-18"` and assert `model["dateLabel"] == "8月18日"`.

- [x] **Step 2: Run tests and verify the missing-module failure**

Run: `python -m unittest tests.test_day_selection -v`

Expected: FAIL because `web/day-selection.mjs` does not exist.

- [x] **Step 3: Implement the pure rules**

Create `web/day-selection.mjs`:

```js
export function nextSelectedDayId(currentDayId, clickedDayId) {
  const clicked = Number(clickedDayId);
  if (!Number.isInteger(clicked)) return currentDayId ?? null;
  return Number(currentDayId) === clicked ? null : clicked;
}

export function routeStyleForSelectedDay(feature, selectedDayId, baseStyle) {
  const style = { ...baseStyle };
  if (selectedDayId === null || selectedDayId === undefined) return style;
  const properties = feature?.properties || {};
  if (properties.optional_branch) return style;
  const featureDayId = Number(properties.day_id);
  if (featureDayId === Number(selectedDayId)) {
    return { ...style, weight: Math.max(Number(style.weight) || 0, 6), opacity: 1 };
  }
  return {
    ...style,
    weight: Math.max(2, (Number(style.weight) || 3) - 1),
    opacity: 0.16,
  };
}
```

Add a local `formatDateLabel(isoDate)` helper in `web/day-card-model.mjs` and expose the result as `dateLabel` from `dayCardModel(day)`. It returns an empty string for an absent or invalid ISO date and formats `2026-08-18` as `8月18日` without relying on the browser timezone.

- [x] **Step 4: Run the focused tests**

Run: `python -m unittest tests.test_day_selection tests.test_day_card_model -v`

Expected: all Day selection and style tests PASS.

- [x] **Step 5: Commit the pure selection unit**

```bash
git add web/day-selection.mjs web/day-card-model.mjs tests/test_day_selection.py tests/test_day_card_model.py
git commit -m "feat: add day route selection rules"
```

### Task 2: Leaflet and Day Card Integration

**Files:**
- Modify: `web/app.mjs`
- Modify: `web/styles.css`
- Modify: `web/index.html`
- Modify: `config/inland-itinerary.json`
- Modify: `route_planner/itinerary.py`
- Modify: `web/route-profile.mjs`
- Modify: `tests/test_web_contract.py`
- Modify: `tests/test_execution_itinerary.py`
- Modify: `tests/test_route_profile.py`

**Interfaces:**
- Consumes: `nextSelectedDayId` and `routeStyleForSelectedDay` from Task 1; existing `stepLayers`, `dayGroups`, `mainLayer`, `roadStyle(feature)`, and rendered Day cards.
- Produces: `toggleDaySelection(dayId)`, `applySelectedDayStyles()`, and synchronized `.is-selected` / `aria-pressed` UI state.

- [x] **Step 1: Add failing web contracts**

Extend `tests/test_web_contract.py` to assert that:

```python
self.assertIn('day-selection.mjs?v=20260818-1', js)
self.assertIn('button.setAttribute("aria-pressed", "false")', js)
self.assertIn('card.dataset.dayId = String(model.day)', js)
self.assertIn('toggleDaySelection(model.day)', js)
self.assertIn('routeStyleForSelectedDay(feature, selectedDayId, roadStyle(feature))', js)
self.assertIn('mainLayer.getBounds()', js)
self.assertIn('.day-card.is-selected', css)
self.assertIn('date.textContent = model.dateLabel', js)
```

Update the app and route-profile cache-version expectations to `20260818-2`, and version the published itinerary URL so deployed browsers cannot reuse stale date data.

- [x] **Step 2: Run the focused contract and verify failure**

Run: `python -m unittest tests.test_web_contract.WebMapContractTests.test_map_renders_day_cards_from_the_execution_itinerary tests.test_web_contract.WebMapContractTests.test_execution_ui_static_assets_have_a_fresh_cache_version tests.test_web_contract.WebMapContractTests.test_day_card_selection_highlights_its_route -v`

Expected: FAIL because selection semantics, integration code, and the new cache version are absent.

- [x] **Step 3: Integrate the selected Day state**

In `web/app.mjs`, import the Task 1 functions and add:

```js
let selectedDayId = null;
const dayCards = new Map();

function applySelectedDayStyles() {
  for (const [feature, layer] of stepLayers.entries()) {
    layer.setStyle(routeStyleForSelectedDay(feature, selectedDayId, roadStyle(feature)));
  }
  for (const [dayId, card] of dayCards.entries()) {
    const selected = dayId === selectedDayId;
    card.classList.toggle("is-selected", selected);
    card.querySelector(".day-card__button")?.setAttribute("aria-pressed", String(selected));
  }
}

function toggleDaySelection(dayId) {
  selectedDayId = nextSelectedDayId(selectedDayId, dayId);
  applySelectedDayStyles();
  const bounds = selectedDayId === null ? mainLayer.getBounds() : dayGroups.get(selectedDayId);
  if (bounds?.isValid()) map.fitBounds(bounds, { padding: [32, 32] });
}
```

When rendering cards, clear `dayCards`, set `card.dataset.dayId`, initialize `aria-pressed="false"`, save the card in `dayCards`, render `model.dateLabel` next to the Day label, and replace `fitDay(model.day)` with `toggleDaySelection(model.day)`.

Add `start_date: 2026-08-14` to `config/inland-itinerary.json`. In `route_planner/itinerary.py`, validate the ISO date and derive each published day's date by adding its Day ID; Day 4 becomes `2026-08-18` and Day 15 becomes `2026-08-29`. Add an execution-itinerary test for the derived sequence and regenerate `web/data/inland-itinerary.json`.

- [x] **Step 4: Add the visible card selection style and refresh asset versions**

Add to `web/styles.css`:

```css
.day-card.is-selected {
  border-color: #2563eb;
  border-left-color: #2563eb;
  background: #eff6ff;
  box-shadow: 0 0 0 2px #bfdbfe;
}
.day-card.is-selected .day-card__button { background: #eff6ff; }
```

Use `20260818-1` for `styles.css`, `app.mjs`, and changed local module import query strings so a deployed browser does not reuse the old behavior.

- [x] **Step 5: Run focused and full tests**

Run: `python -m unittest tests.test_day_selection tests.test_web_contract -v`

Expected: all focused tests PASS.

Run: `python -m unittest discover -s tests -v`

Expected: the full suite PASS with no regressions.

- [x] **Step 6: Verify in the browser**

Open `http://127.0.0.1:8765/`, click a Day card, and confirm its route is the only high-opacity main route and the map fits it. Click another Day and confirm the highlight moves. Click the selected Day again and confirm all route styles and full bounds return. Repeat at a viewport narrower than `860px` and activate a Day button with the keyboard.

- [x] **Step 7: Commit the integration**

```bash
git add web/app.mjs web/styles.css web/index.html web/route-profile.mjs config/inland-itinerary.json route_planner/itinerary.py web/data/inland-itinerary.json tests/test_web_contract.py tests/test_execution_itinerary.py tests/test_route_profile.py
git commit -m "feat: highlight the selected day route"
```
