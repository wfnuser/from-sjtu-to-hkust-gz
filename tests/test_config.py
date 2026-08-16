import json
from pathlib import Path
import tempfile
import unittest

from route_planner.config import load_route_config


class ConfigTests(unittest.TestCase):
    def test_main_route_is_chinese_and_optional_branches_are_disabled(self):
        cfg = load_route_config(Path("config/coastal-route.json"))
        self.assertEqual(cfg.route_id, "coastal-main")
        self.assertEqual(cfg.waypoints[0].name, "上海交通大学闵行校区")
        self.assertEqual(cfg.waypoints[-1].name, "香港科技大学（广州）")
        self.assertIn("杭州阿里巴巴总部", [p.name for p in cfg.waypoints])
        self.assertFalse(cfg.optional_branches["宁波"].enabled)
        self.assertFalse(cfg.optional_branches["深圳"].enabled)

    def test_max_detour_is_exactly_fifteen_percent(self):
        cfg = load_route_config(Path("config/coastal-route.json"))
        self.assertEqual(cfg.max_detour_ratio, 1.15)

    def test_rejects_a_main_route_with_a_non_chinese_display_name(self):
        payload = _valid_payload()
        payload["waypoints"][1]["name"] = "Haining"

        with self.assertRaisesRegex(ValueError, "Chinese"):
            _load_payload(payload)

    def test_rejects_enabled_optional_branch(self):
        payload = _valid_payload()
        payload["optional_branches"]["宁波"]["enabled"] = True

        with self.assertRaisesRegex(ValueError, "disabled"):
            _load_payload(payload)

    def test_rejects_a_route_without_both_endpoints(self):
        payload = _valid_payload()
        payload["waypoints"] = payload["waypoints"][:1]

        with self.assertRaisesRegex(ValueError, "endpoints"):
            _load_payload(payload)

    def test_rejects_a_main_route_with_a_replaced_start_endpoint(self):
        payload = _valid_payload()
        payload["waypoints"][0].update(
            name="上海虹桥站", city="上海", query="上海虹桥站"
        )

        with self.assertRaisesRegex(ValueError, "上海交通大学闵行校区"):
            _load_payload(payload)

    def test_rejects_a_main_route_with_a_replaced_end_endpoint(self):
        payload = _valid_payload()
        payload["waypoints"][-1].update(
            name="广州南站", city="广州", query="广州南站"
        )

        with self.assertRaisesRegex(ValueError, "香港科技大学（广州）"):
            _load_payload(payload)

    def test_rejects_detour_ratio_other_than_fifteen_percent(self):
        payload = _valid_payload()
        payload["max_detour_ratio"] = 1.2

        with self.assertRaisesRegex(ValueError, "1.15"):
            _load_payload(payload)

    def test_loaded_route_mappings_cannot_be_mutated(self):
        cfg = load_route_config(Path("config/coastal-route.json"))

        with self.assertRaises(TypeError):
            cfg.segment_rules["replacement"] = cfg.segment_rules["main-01-to-main-02"]
        with self.assertRaises(TypeError):
            cfg.optional_branches["replacement"] = cfg.optional_branches["宁波"]

    def test_loads_chinese_national_exception_reason(self):
        payload = _valid_payload()
        payload["segment_rules"] = {
            "start-to-end": {
                "allowed_national_m": 1200,
                "national_exception_reason": "平行县道在河道处中断，国道桥为唯一连续铺装通道。",
            }
        }

        cfg = _load_payload(payload)

        self.assertEqual(
            cfg.segment_rules["start-to-end"].national_exception_reason,
            "平行县道在河道处中断，国道桥为唯一连续铺装通道。",
        )

    def test_loads_explicit_short_hard_risk_exception(self):
        payload = _valid_payload()
        payload["segment_rules"] = {
            "start-to-end": {
                "allowed_hard_risk_m": 70,
                "hard_risk_exception_reason": "互通连接段现场观察，必要时下车推行。",
            }
        }

        cfg = _load_payload(payload)
        rule = cfg.segment_rules["start-to-end"]

        self.assertEqual(rule.allowed_hard_risk_m, 70)
        self.assertIn("下车推行", rule.hard_risk_exception_reason)

    def test_loads_reviewed_reroute_decision_metadata(self):
        payload = _valid_payload()
        payload["segment_rules"] = {
            "start-to-end": {
                "reroute_status": "adopted",
                "reroute_reason": "国道由40公里降至4公里。",
            }
        }

        cfg = _load_payload(payload)

        rule = cfg.segment_rules["start-to-end"]
        self.assertEqual(rule.reroute_status, "adopted")
        self.assertEqual(rule.reroute_reason, "国道由40公里降至4公里。")

    def test_loads_bounded_parallel_road_preference(self):
        payload = _valid_payload()
        payload["segment_rules"] = {
            "start-to-end": {
                "parallel_road_available": True,
                "parallel_road_max_extra_m": 2000,
            }
        }

        cfg = _load_payload(payload)

        self.assertEqual(
            cfg.segment_rules["start-to-end"].parallel_road_max_extra_m,
            2000,
        )

    def test_rejects_parallel_road_preference_over_two_kilometres(self):
        payload = _valid_payload()
        payload["segment_rules"] = {
            "start-to-end": {
                "parallel_road_available": True,
                "parallel_road_max_extra_m": 2001,
            }
        }

        with self.assertRaisesRegex(ValueError, "at most 2000"):
            _load_payload(payload)

    def test_loads_evidence_backed_verified_safe_step(self):
        payload = _valid_payload()
        payload["segment_rules"] = {
            "start-to-end": {
                "verified_safe_steps": [
                    {
                        "road_name": "新安江互通",
                        "max_distance_m": 60,
                        "evidence_url": "https://www.openstreetmap.org/way/1376423198",
                        "evidence_note": "平行设施为连续的指定沥青自行车道。",
                    }
                ]
            }
        }

        cfg = _load_payload(payload)
        override = cfg.segment_rules["start-to-end"].verified_safe_steps[0]

        self.assertEqual(override.road_name, "新安江互通")
        self.assertEqual(override.max_distance_m, 60)

    def test_rejects_verified_safe_step_without_https_evidence_or_note(self):
        for evidence_url, evidence_note in (("http://example.com", "有证据"), ("https://example.com", "")):
            with self.subTest(evidence_url=evidence_url, evidence_note=evidence_note):
                payload = _valid_payload()
                payload["segment_rules"] = {
                    "start-to-end": {
                        "verified_safe_steps": [
                            {
                                "road_name": "新安江互通",
                                "max_distance_m": 60,
                                "evidence_url": evidence_url,
                                "evidence_note": evidence_note,
                            }
                        ]
                    }
                }

                with self.assertRaisesRegex(ValueError, "verified_safe_steps"):
                    _load_payload(payload)

    def test_rejects_unknown_reroute_status_and_reason_without_decision(self):
        for rule, message in (
            ({"reroute_status": "maybe", "reroute_reason": "已检查"}, "reroute_status"),
            ({"reroute_reason": "只有原因，没有状态"}, "reroute_reason"),
        ):
            with self.subTest(message=message):
                payload = _valid_payload()
                payload["segment_rules"] = {"start-to-end": rule}
                with self.assertRaisesRegex(ValueError, message):
                    _load_payload(payload)


def _valid_payload():
    return {
        "route_id": "sample",
        "max_detour_ratio": 1.15,
        "waypoints": [
            {
                "id": "start",
                "name": "上海交通大学闵行校区",
                "city": "上海",
                "query": "上海交通大学闵行校区",
                "coordinate": None,
            },
            {
                "id": "end",
                "name": "香港科技大学（广州）",
                "city": "广州",
                "query": "香港科技大学（广州）",
                "coordinate": None,
            },
        ],
        "checkin_waypoints": [],
        "segment_rules": {},
        "optional_branches": {"宁波": {"enabled": False, "waypoints": []}},
    }


def _load_payload(payload):
    with tempfile.TemporaryDirectory() as temporary_directory:
        path = Path(temporary_directory) / "route.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return load_route_config(path)
