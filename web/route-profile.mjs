const PROFILES = {
  execution: {
    id: "execution",
    geojsonUrl: "data/inland-execution-route.geojson",
    summaryUrl: "data/inland-execution-summary.json",
    itineraryUrl: "data/inland-itinerary.json",
    rerouteOptionsUrl: null,
    title: "宇宙骑行路线（江西线）",
    mainLabel: "Day 1–15 执行路线",
    hasOptionalBranches: false,
    showSchedule: false,
    summaryNote: "西溪版本 · 每晚落在可洗衣酒店；点击 Day 卡片聚焦当天路线。",
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
    summaryNote: "当前为内陆审查基线；国道与未分类道路仍在逐段优化。",
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
