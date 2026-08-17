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

function formatDateLabel(isoDate) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(isoDate || ""));
  if (!match) return "";
  const [, year, month, day] = match.map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  if (
    date.getUTCFullYear() !== year
    || date.getUTCMonth() !== month - 1
    || date.getUTCDate() !== day
  ) return "";
  return `${month}月${day}日`;
}

/** Keep completed prelude data available while starting the public itinerary at Day 1. */
export function visibleItineraryDays(itinerary) {
  const days = Array.isArray(itinerary?.days) ? itinerary.days : [];
  const startDay = Number.isInteger(Number(itinerary?.display_start_day))
    ? Number(itinerary.display_start_day)
    : 1;
  return days.filter((day) => Number(day?.day) >= startDay);
}

/** Keep historical route geometry in artifacts while excluding it from the public map. */
export function visibleRouteFeatures(geojson, itinerary) {
  const startDay = Number.isInteger(Number(itinerary?.display_start_day))
    ? Number(itinerary.display_start_day)
    : 1;
  const features = Array.isArray(geojson?.features) ? geojson.features : [];
  return {
    ...geojson,
    features: features.filter((feature) => {
      const dayId = Number(feature?.properties?.day_id);
      return !Number.isInteger(dayId) || dayId >= startDay;
    }),
  };
}

/** Convert one published itinerary day into the decision fields shown in the sidebar. */
export function dayCardModel(day) {
  const lodging = day?.lodging || {};
  const label = `day${Number(day?.day)}`;
  const route = `${day?.from_name || "起点"} → ${day?.to_name || "终点"}`;
  return {
    day: Number(day?.day),
    label,
    dateLabel: formatDateLabel(day?.date),
    status: String(day?.status || "planned"),
    route,
    title: `${label} ${route}`,
    distance: formatDistance(day?.distance_m),
    duration: formatDuration(day?.duration_s),
    waypoints: Array.isArray(day?.key_waypoints) ? day.key_waypoints.map(String) : [],
    lodging: String(lodging.name || ""),
    laundryConfirmed: lodging.laundry === "confirmed",
    riskNote: String(day?.risk_note || ""),
    longDay: Boolean(day?.long_day),
  };
}
