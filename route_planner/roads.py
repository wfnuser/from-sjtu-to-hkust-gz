"""Deterministic road classification and safety-first route selection."""

from collections.abc import Sequence
from dataclasses import dataclass
import re

from route_planner.models import CandidateRoute, RoadClass, SegmentRule


HARD_RISK_TERMS = ("高速", "快速路", "高架", "禁止非机动车", "禁行")
FREIGHT_RISK_TERMS = (
    "疏港",
    "临港",
    "港前",
    "物流",
    "石化",
    "矿区",
    "砂石",
    "高速连接线",
)

_NATIONAL_ROAD = re.compile(r"^\s*G\d{3,4}(?!\d)", re.IGNORECASE)
_PROVINCIAL_ROAD = re.compile(r"^\s*S\d{3}(?!\d)", re.IGNORECASE)
_COUNTY_ROAD = re.compile(r"^\s*[XY]\d{3,4}(?!\d)", re.IGNORECASE)


@dataclass(frozen=True)
class CandidateMetrics:
    national_m: int
    unknown_m: int
    freight_risk_m: int
    hard_risk_m: int


class ReviewRequired(RuntimeError):
    def __init__(self, segment_id: str, reasons: tuple[str, ...]):
        self.segment_id = segment_id
        self.reasons = reasons
        super().__init__(f"{segment_id}: {'; '.join(reasons)}")


def classify_road(road_name: str, instruction: str = "") -> RoadClass:
    """Return the most specific road class identifiable from route text."""
    for text in (road_name, instruction):
        if not text:
            continue
        if _NATIONAL_ROAD.match(text) or "国道" in text:
            return RoadClass.NATIONAL
        if _PROVINCIAL_ROAD.match(text) or "省道" in text:
            return RoadClass.PROVINCIAL
        if _COUNTY_ROAD.match(text) or "县道" in text or "乡道" in text:
            return RoadClass.COUNTY
        if "绿道" in text or "自行车道" in text or "骑行道" in text or "非机动车道" in text:
            return RoadClass.CYCLEWAY
        if "市道" in text or "城市道路" in text or "城市快速路" in text:
            return RoadClass.CITY
    return RoadClass.UNKNOWN


def classify_risks(road_name: str, instruction: str) -> frozenset[str]:
    """Identify hard exclusion and freight-exposure markers in route text."""
    text = f"{road_name} {instruction}"
    tags = set()
    if any(term in text for term in HARD_RISK_TERMS):
        tags.add("hard")
    if any(term in text for term in FREIGHT_RISK_TERMS):
        tags.add("freight")
    return frozenset(tags)


def candidate_metrics(candidate: CandidateRoute) -> CandidateMetrics:
    """Aggregate road-class and safety-risk distances for a candidate."""
    national_m = 0
    unknown_m = 0
    freight_risk_m = 0
    hard_risk_m = 0

    for step in candidate.steps:
        if step.road_class is RoadClass.NATIONAL:
            national_m += step.distance_m
        if step.road_class is RoadClass.UNKNOWN:
            unknown_m += step.distance_m

        risk_tags = step.risk_tags | classify_risks(step.road_name, step.instruction)
        if "freight" in risk_tags:
            freight_risk_m += step.distance_m
        if "hard" in risk_tags:
            hard_risk_m += step.distance_m

    return CandidateMetrics(national_m, unknown_m, freight_risk_m, hard_risk_m)


def choose_candidate(
    candidates: Sequence[CandidateRoute], rule: SegmentRule
) -> CandidateRoute:
    """Select the safest eligible candidate by the stable policy ordering."""
    eligible = []
    for candidate in candidates:
        metrics = candidate_metrics(candidate)
        if metrics.hard_risk_m:
            continue
        if (
            rule.parallel_road_available
            and metrics.national_m > rule.allowed_national_m
        ):
            continue
        eligible.append((candidate, metrics))

    if not eligible:
        raise ReviewRequired(rule.segment_id, ("no eligible safe candidate",))

    return min(
        eligible,
        key=lambda item: (
            item[1].national_m,
            item[1].unknown_m,
            item[1].freight_risk_m,
            item[0].distance_m,
            item[0].duration_s,
            item[0].source_index,
        ),
    )[0]
