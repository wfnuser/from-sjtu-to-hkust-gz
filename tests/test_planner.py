import unittest

from route_planner.models import CandidateRoute, Coordinate, RoadClass, RouteStep, SegmentRule, Waypoint
from route_planner.planner import RoutePlanner
from route_planner.roads import ReviewRequired


START = Waypoint("start", "起点", "上海", "起点", Coordinate(121.0, 31.0))
END = Waypoint("end", "终点", "上海", "终点", Coordinate(121.3, 31.3))
RULE = SegmentRule("a-b", ("S201省道锚点",), True)


class RoutePlannerTests(unittest.TestCase):
    def test_anchors_force_two_sublegs_and_preserve_real_polylines(self):
        fake_client = _FakeAmapClient(
            direct_distance_m=100_000,
            subleg_distances_m=(50_000, 50_000),
        )
        planner = RoutePlanner(fake_client)

        planned = planner.plan_segment(START, END, RULE)

        self.assertEqual(fake_client.call_count, 3)
        self.assertTrue(all(step.polyline_gcj for step in planned.selected.steps))
        self.assertEqual(planned.subleg_distances_m, (50_000, 50_000))

    def test_detour_over_fifteen_percent_creates_review_item(self):
        planned = RoutePlanner(
            _FakeAmapClient(direct_distance_m=100_000, subleg_distances_m=(58_000, 58_000))
        ).plan_segment(START, END, RULE)

        self.assertIn("DETOUR_OVER_15_PERCENT", [review.code for review in planned.reviews])

    def test_subleg_over_eighty_kilometres_creates_review_item(self):
        planned = RoutePlanner(
            _FakeAmapClient(direct_distance_m=100_000, subleg_distances_m=(81_000, 1_000))
        ).plan_segment(START, END, RULE)

        self.assertIn("SUBLEG_OVER_80_KM", [review.code for review in planned.reviews])

    def test_refuses_a_selected_subleg_without_an_api_polyline(self):
        with self.assertRaisesRegex(ReviewRequired, "real API polyline"):
            RoutePlanner(_EmptyRouteClient()).plan_segment(START, END, RULE)


class _FakeAmapClient:
    def __init__(self, *, direct_distance_m, subleg_distances_m):
        self.call_count = 0
        self._direct_distance_m = direct_distance_m
        self._subleg_distances_m = subleg_distances_m
        self._subleg_index = 0

    def geocode(self, query, city):
        if query != "S201省道锚点":
            raise AssertionError(query)
        return (GeocodeAnchor,)

    def electrobike(self, origin, destination):
        self.call_count += 1
        if self.call_count == 1:
            return (_candidate(self._direct_distance_m, 0),)
        distance_m = self._subleg_distances_m[self._subleg_index]
        self._subleg_index += 1
        return (_candidate(distance_m, self._subleg_index),)


class _EmptyRouteClient:
    def geocode(self, query, city):
        return (GeocodeAnchor,)

    def electrobike(self, origin, destination):
        return (CandidateRoute(0, 1_000, 100, ()),)


GeocodeAnchor = type(
    "GeocodeAnchor",
    (),
    {
        "name": "S201省道锚点",
        "formatted_address": "上海市",
        "district": "",
        "location_gcj": Coordinate(121.15, 31.15),
    },
)()


def _candidate(distance_m, source_index):
    return CandidateRoute(
        source_index,
        distance_m,
        distance_m // 5,
        (
            RouteStep(
                "沿县道骑行",
                "X971县道",
                distance_m,
                (Coordinate(121.0, 31.0), Coordinate(121.1, 31.1)),
                RoadClass.COUNTY,
            ),
        ),
    )


if __name__ == "__main__":
    unittest.main()
