/** Return a distinct map style for the original line and its low-national-road detour. */
export function rerouteLineStyle(feature) {
  if (feature?.properties?.route_role === "original") {
    return { color: "#334155", weight: 7, opacity: 0.65, dashArray: "2 8" };
  }
  return { color: "#0891b2", weight: 5, opacity: 0.9, dashArray: "10 7" };
}

/** Pair one detour with the already-published original segment without duplicating GeoJSON. */
export function rerouteFeaturesForOption(option, alternativeFeatures, originalFeatures) {
  const original = originalFeatures
    .filter((feature) => feature?.properties?.segment_id === option.segment_id)
    .map((feature) => ({
      ...feature,
      properties: {
        ...feature.properties,
        ...option,
        candidate_id: option.candidate_id,
        route_role: "original",
      },
    }));
  const alternative = alternativeFeatures.filter(
    (feature) => feature?.properties?.candidate_id === option.candidate_id,
  );
  return [...original, ...alternative];
}

/** Summarize both choices so the rider can decide without hiding the original route. */
export function rerouteComparisonText(option) {
  return `原线 ${formatDistance(option.current_distance_m)}（国道 ${formatDistance(option.current_national_m)}）`
    + `→ 绕行 ${formatDistance(option.alternative_distance_m)}（国道 ${formatDistance(option.alternative_national_m)}）`
    + ` · 多 ${formatDistance(option.distance_delta_m)} / ${formatDuration(option.duration_delta_s)}`
    + ` · 少走国道 ${formatDistance(option.national_reduction_m)}`;
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
