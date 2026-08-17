const PROFILES = {
  execution: {
    id: "execution",
    geojsonUrl: "data/inland-execution-route.geojson",
    summaryUrl: "data/inland-execution-summary.json",
    itineraryUrl: "data/inland-itinerary.json?v=20260818-2",
    rerouteOptionsUrl: null,
    title: "宇宙骑行路线（江西线）",
    mainLabel: "Day 1–15 执行路线",
    hasOptionalBranches: false,
    showSchedule: false,
    summaryNote: "Day 5–15 已压到 115 km 内；三晚小镇酒店的洗衣设施仍需电话确认。",
  },
  inland: {
    id: "inland",
    geojsonUrl: "data/inland-route.geojson",
    summaryUrl: "data/inland-summary.json",
    rerouteOptionsUrl: "data/inland-reroute-options.geojson",
    title: "宇宙骑行路线（江西线）",
    mainLabel: "内陆主线",
    hasOptionalBranches: false,
    showSchedule: false,
    summaryNote: "旧内陆审查基线；仅把距离接近的平行道路作为安全备选。",
  },
  coastal: {
    id: "coastal",
    geojsonUrl: "data/coastal-route.geojson",
    summaryUrl: "data/summary.json",
    rerouteOptionsUrl: null,
    title: "沿海骑行路线",
    mainLabel: "沿海主线",
    hasOptionalBranches: true,
    showSchedule: true,
    summaryNote: "宁波、深圳支线默认关闭，且不计入主线总计。",
  },
};

export function selectRouteProfile(search = "") {
  const requested = new URLSearchParams(search).get("route");
  if (requested === "coastal") return { ...PROFILES.coastal };
  if (requested === "inland") return { ...PROFILES.inland };
  return { ...PROFILES.execution };
}
