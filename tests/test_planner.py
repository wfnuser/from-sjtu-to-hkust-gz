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
        self.assertEqual(planned.subleg_durations_s, (10_000, 10_000))

    def test_detour_over_fifteen_percent_creates_review_item(self):
        planned = RoutePlanner(
            _FakeAmapClient(direct_distance_m=100_000, subleg_distances_m=(58_000, 58_000))
        ).plan_segment(START, END, RULE)

        self.assertIn("DETOUR_OVER_15_PERCENT", [review.code for review in planned.reviews])

    def test_detour_at_exactly_fifteen_percent_does_not_create_review_item(self):
        planned = RoutePlanner(
            _FakeAmapClient(direct_distance_m=100_000, subleg_distances_m=(57_500, 57_500))
        ).plan_segment(START, END, RULE)

        self.assertNotIn("DETOUR_OVER_15_PERCENT", [review.code for review in planned.reviews])

    def test_subleg_over_eighty_kilometres_creates_review_item(self):
        planned = RoutePlanner(
            _FakeAmapClient(direct_distance_m=100_000, subleg_distances_m=(81_000, 1_000))
        ).plan_segment(START, END, RULE)

        self.assertIn("SUBLEG_OVER_80_KM", [review.code for review in planned.reviews])

    def test_subleg_at_exactly_eighty_kilometres_does_not_create_review_item(self):
        planned = RoutePlanner(
            _FakeAmapClient(direct_distance_m=100_000, subleg_distances_m=(80_000, 1_000))
        ).plan_segment(START, END, RULE)

        self.assertNotIn("SUBLEG_OVER_80_KM", [review.code for review in planned.reviews])

    def test_refuses_a_selected_subleg_without_an_api_polyline(self):
        with self.assertRaisesRegex(ReviewRequired, "real API polyline"):
            RoutePlanner(_EmptyRouteClient()).plan_segment(START, END, RULE)

    def test_anchor_can_declare_its_actual_city_for_cross_city_segments(self):
        client = _FakeAmapClient(direct_distance_m=100_000, subleg_distances_m=(50_000, 50_000))
        rule = SegmentRule("a-b", ("深圳::南澳街道",), True)

        RoutePlanner(client).plan_segment(START, END, rule)

        self.assertIn(("南澳街道", "深圳"), client.geocode_calls)

    def test_measured_national_exception_reason_creates_audit_approval(self):
        client = _NationalAmapClient()
        rule = SegmentRule(
            "a-b",
            parallel_road_available=True,
            parallel_road_max_extra_m=2_000,
            allowed_national_m=1_000,
            national_exception_reason="连续铺装的平行县乡道中断，保留国道接驳段。",
        )

        planned = RoutePlanner(client).plan_segment(START, END, rule)

        approvals = [item for item in planned.reviews if item.code == "NATIONAL_ROAD_EXCEPTION_APPROVED"]
        self.assertEqual(len(approvals), 1)
        self.assertEqual(approvals[0].distance_m, 1_000)
        self.assertIn("连续铺装", approvals[0].message)

    def test_short_hard_risk_exception_creates_audit_approval(self):
        rule = SegmentRule(
            "a-b",
            allowed_hard_risk_m=100,
            hard_risk_exception_reason="现场观察，必要时下车推行。",
        )

        planned = RoutePlanner(_HardRiskAmapClient()).plan_segment(START, END, rule)

        approvals = [
            item for item in planned.reviews
            if item.code == "HARD_RISK_EXCEPTION_APPROVED"
        ]
        self.assertEqual(len(approvals), 1)
        self.assertEqual(approvals[0].distance_m, 70)


class _FakeAmapClient:
    def __init__(self, *, direct_distance_m, subleg_distances_m):
        self.call_count = 0
        self._direct_distance_m = direct_distance_m
        self._subleg_distances_m = subleg_distances_m
        self._subleg_index = 0
        self.geocode_calls = []

    def geocode(self, query, city):
        self.geocode_calls.append((query, city))
        if query != "S201省道锚点":
            if (query, city) == ("南澳街道", "深圳"):
                return (ShenzhenGeocodeAnchor,)
            raise AssertionError((query, city))
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


class _NationalAmapClient:
    def electrobike(self, origin, destination):
        return (
            CandidateRoute(
                0,
                1_000,
                200,
                (
                    RouteStep(
                        "沿104国道骑行",
                        "104国道",
                        1_000,
                        (origin, destination),
                        RoadClass.NATIONAL,
                    ),
                ),
            ),
        )


class _HardRiskAmapClient:
    def electrobike(self, origin, destination):
        return (
            CandidateRoute(
                0,
                1_000,
                200,
                (
                    RouteStep(
                        "沿新安江互通骑行70米",
                        "新安江互通",
                        70,
                        (origin, destination),
                        RoadClass.UNKNOWN,
                        frozenset({"hard"}),
                    ),
                    RouteStep(
                        "沿城市道路骑行",
                        "新安东路",
                        930,
                        (origin, destination),
                        RoadClass.CITY,
                    ),
                ),
            ),
        )


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

ShenzhenGeocodeAnchor = type(
    "ShenzhenGeocodeAnchor",
    (),
    {
        "name": "南澳街道",
        "formatted_address": "广东省深圳市龙岗区",
        "district": "龙岗区",
        "location_gcj": Coordinate(114.48, 22.55),
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
