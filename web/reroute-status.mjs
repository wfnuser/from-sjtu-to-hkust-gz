const LABELS = Object.freeze({
  adopted: "已绕行",
  rejected: "保留原线",
  manual_review: "需人工复核",
});

/** Return a compact user-facing label only for reviewed reroute decisions. */
export function rerouteLabel(status) {
  return LABELS[status] || "";
}
