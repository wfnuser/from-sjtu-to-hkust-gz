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

  if (Number(properties.day_id) === Number(selectedDayId)) {
    return {
      ...style,
      weight: Math.max(Number(style.weight) || 0, 6),
      opacity: 1,
    };
  }

  return {
    ...style,
    weight: Math.max(2, (Number(style.weight) || 3) - 1),
    opacity: 0.16,
  };
}
