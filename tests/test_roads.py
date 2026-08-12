import unittest

from route_planner.models import CandidateRoute, Coordinate, RoadClass, RouteStep, SegmentRule
from route_planner.roads import (
    ReviewRequired,
    candidate_metrics,
    choose_candidate,
    classify_risks,
    classify_road,
)


POINT_A = Coordinate(120.0, 27.0)
POINT_B = Coordinate(120.1, 27.1)


def candidate(
    index,
    *,
    national_m=0,
    unknown_m=0,
    freight_risk_m=0,
    hard_risk_m=0,
    distance_m=50_000,
    duration_s=None,
):
    steps = []
    if national_m:
        steps.append(
            RouteStep(
                "沿 G228 骑行",
                "G228丹东线",
                national_m,
                (POINT_A, POINT_B),
                RoadClass.NATIONAL,
            )
        )
    if unknown_m:
        steps.append(
            RouteStep(
                "沿无名道路骑行",
                "无名道路",
                unknown_m,
                (POINT_A, POINT_B),
                RoadClass.UNKNOWN,
            )
        )
    if freight_risk_m:
        steps.append(
            RouteStep(
                "沿疏港路骑行",
                "疏港路",
                freight_risk_m,
                (POINT_A, POINT_B),
                RoadClass.CITY,
            )
        )
    if hard_risk_m:
        steps.append(
            RouteStep(
                "进入快速路",
                "城市快速路",
                hard_risk_m,
                (POINT_A, POINT_B),
                RoadClass.CITY,
                frozenset({"hard"}),
            )
        )
    remainder = distance_m - national_m - unknown_m - freight_risk_m - hard_risk_m
    if remainder:
        steps.append(
            RouteStep(
                "沿县道骑行",
                "X971县道",
                remainder,
                (POINT_A, POINT_B),
                RoadClass.COUNTY,
            )
        )
    return CandidateRoute(
        index,
        distance_m,
        distance_m // 5 if duration_s is None else duration_s,
        tuple(steps),
    )


class RoadClassificationTests(unittest.TestCase):
    def test_classifies_numbered_roads_and_greenways(self):
        self.assertEqual(classify_road("G228丹东线"), RoadClass.NATIONAL)
        self.assertEqual(classify_road("S201省道"), RoadClass.PROVINCIAL)
        self.assertEqual(classify_road("X971县道"), RoadClass.COUNTY)
        self.assertEqual(classify_road("环岛绿道"), RoadClass.CYCLEWAY)
        self.assertEqual(classify_road(""), RoadClass.UNKNOWN)

    def test_classifies_tourism_roads_separately_from_unknown_roads(self):
        for road_name in ("南湖旅游公路", "浰江风景道", "龟峰景区道路", "翁金线"):
            with self.subTest(road_name=road_name):
                self.assertEqual(classify_road(road_name), RoadClass.TOURISM)

    def test_classifies_authoritative_g104_alias_and_auxiliary_as_national(self):
        self.assertEqual(classify_road("京福线"), RoadClass.NATIONAL)
        self.assertEqual(classify_road("京福线辅路"), RoadClass.NATIONAL)
        self.assertEqual(classify_road("", "沿京福线辅路向南骑行"), RoadClass.NATIONAL)

    def test_does_not_classify_embedded_road_numbers(self):
        self.assertEqual(classify_road("前往G228丹东线"), RoadClass.UNKNOWN)

    def test_classifies_risks_from_road_name_and_instruction(self):
        self.assertEqual(classify_risks("疏港大道", "进入快速路"), frozenset({"freight", "hard"}))

    def test_classifies_observed_expressway_and_freight_connectors(self):
        self.assertIn("hard", classify_risks("S55秀永支线入口", "向前骑行"))
        self.assertIn("hard", classify_risks("萧江互通", "向前骑行"))
        self.assertIn("hard", classify_risks("收费站匝道", "向前骑行"))
        self.assertIn("freight", classify_risks("通港路辅路", "向前骑行"))
        self.assertIn("freight", classify_risks("兴港路", "向前骑行"))


class CandidateSelectionTests(unittest.TestCase):
    def test_candidate_metrics_total_classification_and_risk_distances(self):
        metrics = candidate_metrics(
            candidate(0, national_m=900, unknown_m=800, freight_risk_m=700, hard_risk_m=600)
        )

        self.assertEqual(metrics.national_m, 900)
        self.assertEqual(metrics.unknown_m, 800)
        self.assertEqual(metrics.freight_risk_m, 700)
        self.assertEqual(metrics.hard_risk_m, 600)

    def test_parallel_provincial_road_makes_national_candidate_ineligible(self):
        national = candidate(0, national_m=9000, distance_m=50_000)
        provincial = candidate(1, national_m=0, distance_m=55_500)
        rule = SegmentRule("霞浦-宁德", parallel_road_available=True)

        self.assertIs(choose_candidate([national, provincial], rule), provincial)

    def test_reviewed_preferred_candidate_wins_over_shorter_safe_candidate(self):
        shorter = candidate(0, distance_m=13_000)
        reviewed = candidate(2, distance_m=14_500)
        rule = SegmentRule("a-b", preferred_candidate_index=2)

        self.assertIs(choose_candidate([shorter, reviewed], rule), reviewed)

    def test_raises_review_when_preferred_candidate_is_not_eligible(self):
        safe = candidate(0, distance_m=13_000)
        unsafe_reviewed = candidate(2, hard_risk_m=100, distance_m=14_500)
        rule = SegmentRule("a-b", preferred_candidate_index=2)

        with self.assertRaises(ReviewRequired) as caught:
            choose_candidate([safe, unsafe_reviewed], rule)

        self.assertEqual(
            caught.exception.reasons,
            ("preferred candidate is unavailable or unsafe",),
        )

    def test_hard_risk_never_wins_even_if_shorter(self):
        expressway = candidate(0, hard_risk_m=1000, distance_m=30_000)
        county = candidate(1, hard_risk_m=0, distance_m=34_000)

        self.assertIs(choose_candidate([expressway, county], SegmentRule("a-b")), county)

    def test_freight_risk_is_ineligible_even_if_shorter(self):
        freight = candidate(0, freight_risk_m=100, distance_m=30_000)
        county = candidate(1, distance_m=34_000)

        self.assertIs(choose_candidate([freight, county], SegmentRule("a-b")), county)

    def test_raises_review_when_all_candidates_have_freight_risk(self):
        with self.assertRaises(ReviewRequired):
            choose_candidate([candidate(0, freight_risk_m=100)], SegmentRule("a-b"))

    def test_parallel_road_rule_allows_national_distance_at_the_limit(self):
        at_limit = candidate(0, national_m=1000, distance_m=30_000)
        over_limit = candidate(1, national_m=1001, distance_m=20_000)
        rule = SegmentRule("a-b", parallel_road_available=True, allowed_national_m=1000)

        self.assertIs(choose_candidate([over_limit, at_limit], rule), at_limit)

    def test_selection_prioritizes_lower_national_distance_over_total_distance(self):
        lower_national = candidate(0, national_m=200, distance_m=50_000)
        more_national = candidate(1, national_m=300, distance_m=20_000)

        self.assertIs(
            choose_candidate(
                [more_national, lower_national],
                SegmentRule("a-b"),
            ),
            lower_national,
        )

    def test_unknown_candidate_remains_eligible_when_alternative_has_freight_risk(self):
        freight = candidate(0, freight_risk_m=100, distance_m=50_000)
        more_unknown = candidate(1, unknown_m=50, distance_m=10_000)

        self.assertIs(
            choose_candidate([more_unknown, freight], SegmentRule("a-b")),
            more_unknown,
        )

    def test_selection_prioritizes_lower_freight_risk_before_distance(self):
        lower_freight = candidate(0, distance_m=50_000)
        more_freight = candidate(1, freight_risk_m=100, distance_m=10_000)

        self.assertIs(
            choose_candidate([more_freight, lower_freight], SegmentRule("a-b")),
            lower_freight,
        )

    def test_distance_duration_and_source_index_break_safety_ties(self):
        longer = candidate(0, distance_m=20_000, duration_s=100)
        slower = candidate(1, distance_m=10_000, duration_s=200)
        later = candidate(2, distance_m=10_000, duration_s=100)
        earlier = candidate(1, distance_m=10_000, duration_s=100)

        self.assertIs(
            choose_candidate([longer, slower, later, earlier], SegmentRule("a-b")),
            earlier,
        )

    def test_raises_review_when_all_candidates_have_hard_risk(self):
        with self.assertRaises(ReviewRequired) as caught:
            choose_candidate([candidate(0, hard_risk_m=100)], SegmentRule("a-b"))

        self.assertEqual(caught.exception.segment_id, "a-b")
        self.assertEqual(caught.exception.reasons, ("no eligible safe candidate",))

    def test_raises_review_when_parallel_road_excludes_all_national_routes(self):
        with self.assertRaises(ReviewRequired) as caught:
            choose_candidate(
                [candidate(0, national_m=1)],
                SegmentRule("a-b", parallel_road_available=True),
            )

        self.assertEqual(caught.exception.reasons, ("no eligible safe candidate",))


if __name__ == "__main__":
    unittest.main()
