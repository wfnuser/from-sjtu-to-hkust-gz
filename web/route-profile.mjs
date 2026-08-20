const PROFILES = {
  execution: {
    id: "execution",
    geojsonUrl: "data/inland-execution-route.geojson",
    summaryUrl: "data/inland-execution-summary.json",
    itineraryUrl: "data/inland-itinerary.json?v=20260819-2",
    rerouteOptionsUrl: null,
    title: "宇宙骑行路线（江西线）",
    mainLabel: "Day 1–16 执行路线",
    hasOptionalBranches: false,
    showSchedule: false,
    summaryNote: "Day 7–15 约 79–113 km；Day 16 为短抵达日；每天直达住宿，不设置固定中途停靠。",
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
