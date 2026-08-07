const GEOJSON_URL = "data/coastal-route.geojson";
const SUMMARY_URL = "data/summary.json";
const BRANCH_IDS = new Set(["main", "ningbo", "shenzhen"]);

const ROAD_STYLES = {
  cycleway: { color: "#7c3aed", weight: 5, opacity: 0.9 },
  county: { color: "#16a34a", weight: 4, opacity: 0.9 },
  tourism: { color: "#16a34a", weight: 4, opacity: 0.9 },
  provincial: { color: "#2563eb", weight: 4, opacity: 0.9 },
  national: { color: "#f97316", weight: 5, opacity: 0.9 },
  unknown: { color: "#64748b", weight: 3, opacity: 0.8 },
  city: { color: "#64748b", weight: 3, opacity: 0.8 },
};

const ROAD_LABELS = {
  cycleway: "骑行道",
  county: "县道",
  tourism: "旅游道路",
  provincial: "省道",
  national: "国道",
  city: "城市道路",
  unknown: "未分类道路",
};

const map = L.map("map", { zoomControl: true, preferCanvas: true }).setView([27.2, 119.5], 5);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
}).addTo(map);

const mainLayer = L.featureGroup().addTo(map);
const optionalLayers = {
  ningbo: L.featureGroup(),
  shenzhen: L.featureGroup(),
};
const segmentGroups = new Map();
const stepLayers = new Map();

const elements = {
  cards: document.querySelector("#segment-cards"),
  count: document.querySelector("#segment-count"),
  mainTotals: document.querySelector("#main-totals"),
  mapMessage: document.querySelector("#map-message"),
  reviewCount: document.querySelector("#review-count"),
  reviewList: document.querySelector("#review-list"),
  reviewPanel: document.querySelector("#review-panel"),
  routeStatus: document.querySelector("#route-status"),
  ningboCheckbox: document.querySelector("#ningbo-branch"),
  shenzhenCheckbox: document.querySelector("#shenzhen-branch"),
};

/** Return the Leaflet path style for one published road-step feature. */
export function roadStyle(feature) {
  const properties = feature.properties || {};
  if (properties.optional_branch) {
    return { color: "#64748b", weight: 4, opacity: 0.9, dashArray: "8 7" };
  }
  if (isHardReview(properties)) {
    return { color: "#dc2626", weight: 5, opacity: 0.95 };
  }
  return ROAD_STYLES[properties.road_class] || ROAD_STYLES.unknown;
}

/** Render the published main-route totals; optional totals deliberately stay separate. */
function renderMainTotals(summary) {
  const main = summary.main || {};
  const reviewCount = Number(main.unresolved_count || 0);
  elements.mainTotals.innerHTML = "";
  const values = [
    ["距离", formatDistance(main.distance_m)],
    ["预计骑行", formatDuration(main.duration_s)],
    ["待复核", reviewCount ? `${reviewCount} 段` : "无"],
  ];
  for (const [label, value] of values) {
    const wrapper = document.createElement("div");
    const term = document.createElement("dt");
    const detail = document.createElement("dd");
    term.textContent = label;
    detail.textContent = value;
    wrapper.append(term, detail);
    elements.mainTotals.append(wrapper);
  }
}

/** Render segment buttons from real feature groups; each button zooms only to its own roads. */
export function renderSegmentCards(summary) {
  renderMainTotals(summary);
  elements.cards.innerHTML = "";
  const entries = [...segmentGroups.values()];
  const daySummaries = new Map((summary.days || []).map((item) => [Number(item.day), item]));
  elements.count.textContent = entries.length ? `${entries.length} 段` : "";

  let currentDay = null;
  entries.forEach((entry, index) => {
    const first = entry.features[0].properties || {};
    const day = Number(entry.day);
    if (!entry.optional && Number.isInteger(day) && day !== currentDay) {
      currentDay = day;
      const daySummary = daySummaries.get(day) || {};
      const heading = document.createElement("h3");
      heading.className = "day-heading";
      heading.textContent = `第 ${day} 天 · ${formatDistance(daySummary.distance_m)}`;
      elements.cards.append(heading);
    }
    const card = document.createElement("button");
    card.type = "button";
    card.className = `segment-card${entry.optional ? " is-optional" : ""}`;
    card.setAttribute("aria-label", `查看第 ${index + 1} 段：${first.from_name || "起点"}至${first.to_name || "终点"}`);

    const route = document.createElement("span");
    route.className = "segment-card__route";
    route.textContent = `${first.from_name || "起点"} → ${first.to_name || "终点"}`;
    const meta = document.createElement("span");
    meta.className = "segment-card__meta";
    meta.textContent = `${entry.optional ? "可选支线 · " : ""}${formatDistance(sumDistance(entry.features))} · ${entry.features.length} 个道路步骤`;
    card.append(route, meta);
    card.addEventListener("click", () => fitSegment(entry));
    elements.cards.append(card);
  });
}

/** Show or hide optional branches without changing the published main totals. */
export function setOptionalBranchesVisible(enabled) {
  const visibleBranches = new Set();
  if (enabled && elements.ningboCheckbox.checked) visibleBranches.add("ningbo");
  if (enabled && elements.shenzhenCheckbox.checked) visibleBranches.add("shenzhen");

  for (const [branch, layer] of Object.entries(optionalLayers)) {
    if (visibleBranches.has(branch)) {
      layer.addTo(map);
    } else {
      map.removeLayer(layer);
    }
  }
}

function addFeatures(geojson) {
  const features = Array.isArray(geojson.features) ? geojson.features : [];
  const roadFeatures = features.filter(isRoadLine);
  for (const feature of roadFeatures) validateBranchFeature(feature.properties || {});
  for (const feature of roadFeatures) {
    const properties = feature.properties || {};
    const segmentId = String(properties.segment_id || "未命名路段");
    let entry = segmentGroups.get(segmentId);
    if (!entry) {
      entry = {
        id: segmentId,
        features: [],
        group: L.featureGroup(),
        optional: Boolean(properties.optional_branch),
        branch: properties.branch_id,
        day: properties.day,
      };
      segmentGroups.set(segmentId, entry);
    }

    const stepLayer = L.geoJSON(feature, { style: roadStyle });
    stepLayer.bindPopup(popupContent(properties));
    stepLayers.set(feature, stepLayer);
    entry.group.addLayer(stepLayer);
    entry.features.push(feature);
  }

  for (const entry of segmentGroups.values()) {
    if (entry.optional) {
      const targetLayer = optionalLayers[entry.branch];
      if (targetLayer) targetLayer.addLayer(entry.group);
    } else {
      mainLayer.addLayer(entry.group);
    }
  }
}

function renderReviews() {
  const reviews = [];
  for (const entry of segmentGroups.values()) {
    for (const feature of entry.features) {
      if (isHardReview(feature.properties || {})) {
        reviews.push({ entry, feature, stepLayer: stepLayers.get(feature) });
      }
    }
  }

  elements.reviewList.innerHTML = "";
  elements.reviewPanel.hidden = reviews.length === 0;
  elements.reviewCount.textContent = reviews.length ? `${reviews.length} 项` : "";
  for (const { entry, feature, stepLayer } of reviews) {
    const properties = feature.properties || {};
    const item = document.createElement("li");
    const link = document.createElement("button");
    link.type = "button";
    link.className = "review-link";
    link.innerHTML = `<strong>待复核</strong> · ${escapeHtml(properties.road_name || "未命名道路")}<br>${escapeHtml(properties.from_name || "起点")} → ${escapeHtml(properties.to_name || "终点")}`;
    link.addEventListener("click", () => fitReviewFeature(entry, stepLayer));
    item.append(link);
    elements.reviewList.append(item);
  }
}

function fitSegment(entry) {
  const bounds = entry.group.getBounds();
  if (bounds.isValid()) map.fitBounds(bounds, { padding: [32, 32] });
}

function fitReviewFeature(entry, stepLayer) {
  revealReviewBranch(entry);
  const bounds = stepLayer?.getBounds();
  if (!bounds?.isValid()) return;
  map.fitBounds(bounds, { padding: [32, 32] });
  stepLayer.openPopup();
}

function revealReviewBranch(entry) {
  if (!entry.optional) return;
  if (entry.branch === "ningbo") elements.ningboCheckbox.checked = true;
  if (entry.branch === "shenzhen") elements.shenzhenCheckbox.checked = true;
  optionalLayers[entry.branch]?.addTo(map);
}

function popupContent(properties) {
  const roadClass = properties.road_class || "unknown";
  const review = reviewLabel(properties.review_status);
  return `
    <h3 class="popup-title">${escapeHtml(properties.road_name || "未命名道路")}</h3>
    <p class="popup-detail"><strong>道路分类：</strong>${escapeHtml(ROAD_LABELS[roadClass] || "未分类道路")}</p>
    <p class="popup-detail"><strong>分类依据：</strong>发布的 API 道路步骤分类（${escapeHtml(roadClass)}）</p>
    <p class="popup-detail"><strong>距离：</strong>${formatDistance(properties.distance_m)}</p>
    <p class="popup-detail"><strong>复核状态：</strong>${review}</p>
  `;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]);
}

function validateBranchFeature(properties) {
  const branchId = properties.branch_id;
  if (!BRANCH_IDS.has(branchId)) {
    throw invalidBranchError();
  }
  if (Boolean(properties.optional_branch) !== (branchId !== "main")) {
    throw invalidBranchError();
  }
}

function invalidBranchError() {
  const error = new Error("Unknown published branch_id");
  error.name = "InvalidBranchError";
  return error;
}

function isRoadLine(feature) {
  const coordinates = feature?.geometry?.coordinates;
  return feature?.geometry?.type === "LineString" && Array.isArray(coordinates) && coordinates.length > 1;
}

function isHardReview(properties) {
  return ["review_required", "unresolved", "hard_review"].includes(properties.review_status)
    || (Array.isArray(properties.risk_tags) && properties.risk_tags.includes("hard"));
}

function reviewLabel(status) {
  return ({ approved: "已通过", review_required: "需人工复核", unresolved: "未解析", hard_review: "需人工复核" })[status] || "未标注";
}

function sumDistance(features) {
  return features.reduce((total, feature) => total + Number(feature.properties?.distance_m || 0), 0);
}

function formatDistance(meters) {
  const value = Number(meters);
  if (!Number.isFinite(value) || value < 0) return "—";
  return value >= 1000 ? `${(value / 1000).toFixed(value >= 10000 ? 0 : 1)} km` : `${Math.round(value)} m`;
}

function formatDuration(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value < 0) return "—";
  const hours = Math.floor(value / 3600);
  const minutes = Math.round((value % 3600) / 60);
  return hours ? `${hours} 小时${minutes ? ` ${minutes} 分` : ""}` : `${minutes} 分`;
}

function showEmptyState() {
  showDataError("路线数据尚未生成", "未生成");
}

function showDataError(message, status = "数据无效") {
  elements.mapMessage.textContent = message;
  elements.mapMessage.hidden = false;
  elements.routeStatus.textContent = status;
  elements.routeStatus.className = "status-badge is-warning";
  elements.cards.innerHTML = `<p class="intro">${message}</p>`;
}

function showReadyState() {
  elements.mapMessage.hidden = true;
  elements.routeStatus.textContent = "已载入";
  elements.routeStatus.className = "status-badge is-ready";
}

async function loadRoute() {
  try {
    const [geojsonResponse, summaryResponse] = await Promise.all([
      fetch(GEOJSON_URL),
      fetch(SUMMARY_URL),
    ]);
    if (!geojsonResponse.ok || !summaryResponse.ok) throw new Error("Route artifacts are unavailable");
    const [geojson, summary] = await Promise.all([geojsonResponse.json(), summaryResponse.json()]);
    addFeatures(geojson);
    if (!segmentGroups.size) throw new Error("No published road steps");
    renderSegmentCards(summary);
    renderReviews();
    const bounds = mainLayer.getBounds();
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [32, 32] });
    showReadyState();
  } catch (error) {
    if (error?.name === "InvalidBranchError") {
      showDataError("路线数据支线标识无效");
    } else {
      showEmptyState();
    }
    console.warn("Unable to load published route artifacts.", error);
  }
}

elements.ningboCheckbox.addEventListener("change", () => setOptionalBranchesVisible(true));
elements.shenzhenCheckbox.addEventListener("change", () => setOptionalBranchesVisible(true));
setOptionalBranchesVisible(false);
loadRoute();
