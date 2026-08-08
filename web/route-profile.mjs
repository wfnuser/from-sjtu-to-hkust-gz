const PROFILES = {
  inland: {
    id: "inland",
    geojsonUrl: "data/inland-route.geojson",
    summaryUrl: "data/inland-summary.json",
    title: "内陆电助力骑行路线",
    mainLabel: "内陆主线",
    hasOptionalBranches: false,
    showSchedule: false,
    summaryNote: "当前为内陆审查基线；国道与未分类道路仍在逐段优化。",
  },
  coastal: {
    id: "coastal",
    geojsonUrl: "data/coastal-route.geojson",
    summaryUrl: "data/summary.json",
    title: "沿海电助力骑行路线",
    mainLabel: "沿海主线",
    hasOptionalBranches: true,
    showSchedule: true,
    summaryNote: "宁波、深圳支线默认关闭，且不计入主线总计。",
  },
};

export function selectRouteProfile(search = "") {
  const requested = new URLSearchParams(search).get("route");
  return { ...(requested === "coastal" ? PROFILES.coastal : PROFILES.inland) };
}
