from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType


class RoadClass(str, Enum):
    CYCLEWAY = "cycleway"
    TOURISM = "tourism"
    COUNTY = "county"
    PROVINCIAL = "provincial"
    CITY = "city"
    NATIONAL = "national"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Coordinate:
    lon: float
    lat: float


@dataclass(frozen=True)
class SegmentRule:
    segment_id: str
    anchor_queries: tuple[str, ...] = ()
    parallel_road_available: bool = False
    allowed_national_m: int = 0
    day: int | None = None
    national_exception_reason: str = ""
    reroute_status: str = "unreviewed"
    reroute_reason: str = ""
    preferred_candidate_index: int | None = None


@dataclass(frozen=True)
class Waypoint:
    id: str
    name: str
    city: str
    query: str
    coordinate: Coordinate | None = None
    required: bool = True
    include_in_main_totals: bool = True
    branch: str = "main"


@dataclass(frozen=True)
class OptionalBranch:
    name: str
    enabled: bool
    waypoints: tuple[Waypoint, ...]


@dataclass(frozen=True)
class RouteConfig:
    route_id: str
    max_detour_ratio: float
    waypoints: tuple[Waypoint, ...]
    checkin_waypoints: tuple[Waypoint, ...]
    segment_rules: Mapping[str, SegmentRule]
    optional_branches: Mapping[str, OptionalBranch]

    def __post_init__(self) -> None:
        object.__setattr__(self, "segment_rules", MappingProxyType(dict(self.segment_rules)))
        object.__setattr__(
            self, "optional_branches", MappingProxyType(dict(self.optional_branches))
        )


@dataclass(frozen=True)
class RouteStep:
    instruction: str
    road_name: str
    distance_m: int
    polyline_gcj: tuple[Coordinate, ...]
    road_class: RoadClass
    risk_tags: frozenset[str] = frozenset()


@dataclass(frozen=True)
class CandidateRoute:
    source_index: int
    distance_m: int
    duration_s: int
    steps: tuple[RouteStep, ...]


@dataclass(frozen=True)
class GeocodeCandidate:
    name: str
    formatted_address: str
    district: str
    location_gcj: Coordinate
    poi_id: str = ""


@dataclass(frozen=True)
class PoiResolution:
    query: str
    city: str
    candidates: tuple[GeocodeCandidate, ...]
    selected: GeocodeCandidate | None


@dataclass(frozen=True)
class ResolutionReport:
    resolutions: tuple[PoiResolution, ...]
    unresolved_queries: tuple[str, ...]


@dataclass(frozen=True)
class ReviewItem:
    code: str
    segment_id: str
    severity: str
    message: str
    road_name: str = ""
    distance_m: int = 0


@dataclass(frozen=True)
class PlannedSegment:
    segment_id: str
    from_waypoint: Waypoint
    to_waypoint: Waypoint
    rule: SegmentRule
    baseline_distance_m: int
    selected: CandidateRoute
    detour_ratio: float
    subleg_distances_m: tuple[int, ...]
    reviews: tuple[ReviewItem, ...] = ()
    subleg_durations_s: tuple[int, ...] = ()
