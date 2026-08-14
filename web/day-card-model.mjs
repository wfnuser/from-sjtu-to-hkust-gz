function formatDistance(meters) {
  const value = Number(meters);
  if (!Number.isFinite(value) || value < 0) return "—";
  return `${(value / 1000).toFixed(1)} km`;
}

function formatDuration(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value < 0) return "—";
  const hours = Math.floor(value / 3600);
  const minutes = Math.round((value % 3600) / 60);
  return hours ? `${hours} 小时 ${minutes} 分` : `${minutes} 分`;
}

/** Convert one published itinerary day into the decision fields shown in the sidebar. */
export function dayCardModel(day) {
  const lodging = day?.lodging || {};
  return {
    day: Number(day?.day),
    label: `Day ${Number(day?.day)}`,
    status: String(day?.status || "planned"),
    route: `${day?.from_name || "起点"} → ${day?.to_name || "终点"}`,
    distance: formatDistance(day?.distance_m),
    duration: formatDuration(day?.duration_s),
    waypoints: Array.isArray(day?.key_waypoints) ? day.key_waypoints.map(String) : [],
    lodging: String(lodging.name || ""),
    laundryConfirmed: lodging.laundry === "confirmed",
    riskNote: String(day?.risk_note || ""),
    longDay: Boolean(day?.long_day),
  };
}
