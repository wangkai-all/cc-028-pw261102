import unittest
from datetime import datetime

from backend.db import Repository
from backend.domain import (
    business_seconds,
    compute_alerts,
    parse_bj,
    reconstruct,
)
from backend.importer import import_scans


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


class BusinessClockTests(unittest.TestCase):
    def test_weekend_and_holidays_are_skipped(self):
        start = parse_bj("2026-10-01T10:00:00+08:00")
        end = parse_bj("2026-10-08T10:00:00+08:00")
        holidays = {parse_bj(f"2026-10-0{i}").date(): "国庆长假" for i in range(1, 8)}
        seconds = business_seconds(start, end, holidays)
        # 2026-10-01 到 10-07 全部跳过；10-08 只累计 09:00-10:00 的 1 小时。
        self.assertEqual(seconds, 3600)

    def test_work_window_is_clipped_to_nine_to_eighteen(self):
        start = parse_bj("2026-11-09T08:30:00+08:00")
        end = parse_bj("2026-11-09T19:30:00+08:00")
        self.assertEqual(business_seconds(start, end, {}), 9 * 3600)


class ReconstructionTests(unittest.TestCase):
    def setUp(self):
        self.repo = Repository(":memory:")
        self.repo.add_carrier("SF", "顺丰", 1)
        for code, canonical in [
            ("PICK", "PICKED_UP"),
            ("MOVE", "IN_TRANSIT"),
            ("HUB", "ARRIVED"),
            ("DELIVER", "OUT_FOR_DELIVERY"),
            ("SIGN", "DELIVERED"),
        ]:
            self.repo.add_mapping("SF", code, code, canonical)
        self.mappings = self.repo.mapping_dict()
        self.package = {
            "tracking_no": "T1",
            "carrier": "SF",
            "carrier_name": "顺丰",
            "display_name": "测试件",
            "origin": "北京",
            "destination": "上海",
        }

    def test_late_scan_sorts_by_occurrence_and_does_not_revert_delivered(self):
        records = [
            {
                "scan_id": "1",
                "tracking_no": "T1",
                "carrier": "SF",
                "status_code": "PICK",
                "occurred_at": "2026-11-09T09:00:00+08:00",
                "received_at": "2026-11-09T09:05:00+08:00",
                "location": "北京",
            },
            {
                "scan_id": "2",
                "tracking_no": "T1",
                "carrier": "SF",
                "status_code": "MOVE",
                "occurred_at": "2026-11-09T10:00:00+08:00",
                "received_at": "2026-11-09T10:05:00+08:00",
                "location": "分拨中心",
            },
            {
                "scan_id": "3",
                "tracking_no": "T1",
                "carrier": "SF",
                "status_code": "SIGN",
                "occurred_at": "2026-11-09T12:00:00+08:00",
                "received_at": "2026-11-09T12:05:00+08:00",
                "location": "上海",
            },
            # 晚到的运输扫描发生在签收之前，但系统在很久后才收到。
            {
                "scan_id": "4",
                "tracking_no": "T1",
                "carrier": "SF",
                "status_code": "MOVE",
                "occurred_at": "2026-11-09T11:00:00+08:00",
                "received_at": "2026-11-12T15:00:00+08:00",
                "location": "晚到节点",
            },
            # 签收之后的运输回退必须是异常，不把状态打回运输中。
            {
                "scan_id": "5",
                "tracking_no": "T1",
                "carrier": "SF",
                "status_code": "MOVE",
                "occurred_at": "2026-11-09T13:00:00+08:00",
                "received_at": "2026-11-12T15:05:00+08:00",
                "location": "异常回退",
            },
        ]
        result = import_scans(self.repo, records, "unit-test", "SF")
        self.assertEqual(result["inserted_count"], 5)

        as_of = parse_bj("2026-11-12T18:00:00+08:00")
        analysis = reconstruct(
            self.package,
            self.repo.scan_rows("T1"),
            self.mappings,
            {},
            as_of,
        )
        self.assertEqual(analysis.status, "DELIVERED")
        self.assertEqual([event.scan_id for event in analysis.timeline], ["1", "2", "4", "3", "5"])
        self.assertTrue(analysis.timeline[2].late_arrival)
        self.assertEqual(analysis.timeline[-1].anomaly_code, "REGRESSION")
        self.assertFalse(analysis.timeline[-1].is_effective)

    def test_unknown_status_is_anomaly_without_progress(self):
        records = [
            {
                "scan_id": "10",
                "tracking_no": "T1",
                "carrier": "SF",
                "status_code": "PICK",
                "occurred_at": "2026-11-09T09:00:00+08:00",
                "received_at": "2026-11-09T09:05:00+08:00",
            },
            {
                "scan_id": "11",
                "tracking_no": "T1",
                "carrier": "SF",
                "status_code": "MYSTERY",
                "occurred_at": "2026-11-09T10:00:00+08:00",
                "received_at": "2026-11-09T10:05:00+08:00",
            },
        ]
        import_scans(self.repo, records, "unit-test", "SF")
        analysis = reconstruct(
            self.package,
            self.repo.scan_rows("T1"),
            self.mappings,
            {},
            parse_bj("2026-11-09T18:00:00+08:00"),
        )
        self.assertEqual(analysis.status, "PICKED_UP")
        self.assertEqual(analysis.anomalies[0]["code"], "UNKNOWN_STATUS")
        self.assertFalse(analysis.timeline[1].is_effective)

    def test_observation_time_excludes_future_scans(self):
        records = [
            {
                "scan_id": "20",
                "tracking_no": "T1",
                "carrier": "SF",
                "status_code": "PICK",
                "occurred_at": "2026-11-09T09:00:00+08:00",
                "received_at": "2026-11-09T09:00:00+08:00",
            },
            {
                "scan_id": "21",
                "tracking_no": "T1",
                "carrier": "SF",
                "status_code": "SIGN",
                "occurred_at": "2026-11-10T10:00:00+08:00",
                "received_at": "2026-11-09T15:00:00+08:00",
            },
        ]
        import_scans(self.repo, records, "unit-test", "SF")
        analysis = reconstruct(
            self.package,
            self.repo.scan_rows("T1"),
            self.mappings,
            {},
            parse_bj("2026-11-09T18:00:00+08:00"),
        )
        self.assertEqual(analysis.status, "PICKED_UP")
        self.assertEqual(analysis.ignored_future_count, 1)

    def test_stall_requires_four_business_hours(self):
        records = [
            {
                "scan_id": "30",
                "tracking_no": "T1",
                "carrier": "SF",
                "status_code": "MOVE",
                "occurred_at": "2026-11-09T09:00:00+08:00",
                "received_at": "2026-11-09T09:00:00+08:00",
            }
        ]
        import_scans(self.repo, records, "unit-test", "SF")
        as_of = parse_bj("2026-11-09T12:59:00+08:00")
        analysis = reconstruct(
            self.package,
            self.repo.scan_rows("T1"),
            self.mappings,
            {},
            as_of,
        )
        self.assertEqual(compute_alerts(analysis, as_of, {}), [])
        as_of = parse_bj("2026-11-09T13:01:00+08:00")
        alerts = compute_alerts(analysis, as_of, {})
        self.assertEqual([alert["type"] for alert in alerts], ["STALLED"])

    def test_duplicate_scan_id_is_skipped(self):
        record = {
            "scan_id": "DUP",
            "tracking_no": "T1",
            "carrier": "SF",
            "status_code": "PICK",
            "occurred_at": "2026-11-09T09:00:00+08:00",
            "received_at": "2026-11-09T09:00:00+08:00",
        }
        first = import_scans(self.repo, [record], "first", "SF")
        second = import_scans(self.repo, [record], "second", "SF")
        self.assertEqual(first["inserted_count"], 1)
        self.assertEqual(second["inserted_count"], 0)
        self.assertEqual(second["duplicate_count"], 1)
        self.assertEqual(len(self.repo.scan_rows("T1")), 1)

    def test_empty_import_creates_zero_count_batch(self):
        result = import_scans(self.repo, [], "empty", "SF")
        self.assertEqual(result["received_count"], 0)
        self.assertEqual(result["inserted_count"], 0)
        self.assertEqual(result["duplicate_count"], 0)
        self.assertEqual(self.repo.import_batches()[0]["received_count"], 0)

    def test_recalculate_keeps_one_current_alert_and_records_clearing(self):
        import_scans(
            self.repo,
            [
                {
                    "scan_id": "40",
                    "tracking_no": "T1",
                    "carrier": "SF",
                    "status_code": "MOVE",
                    "occurred_at": "2026-11-09T09:00:00+08:00",
                    "received_at": "2026-11-09T09:00:00+08:00",
                }
            ],
            "unit-test",
            "SF",
        )
        as_of = parse_bj("2026-11-09T13:01:00+08:00")
        first = self.repo.recalculate(as_of)
        second = self.repo.recalculate(as_of)
        self.assertEqual(first["created"], 1)
        self.assertEqual(second["created"], 0)
        self.assertEqual(second["unchanged"], 1)
        current = self.repo.current_alerts()
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0]["alert_type"], "STALLED")

        # 补入 12:30 的到站扫描后，到 13:01 只等待 31 分钟，停滞应解除。
        import_scans(
            self.repo,
            [
                {
                    "scan_id": "41",
                    "tracking_no": "T1",
                    "carrier": "SF",
                    "status_code": "HUB",
                    "occurred_at": "2026-11-09T12:30:00+08:00",
                    "received_at": "2026-11-09T13:01:00+08:00",
                }
            ],
            "supplement",
            "SF",
        )
        cleared = self.repo.recalculate(as_of)
        self.assertEqual(cleared["cleared"], 1)
        current = self.repo.current_alerts()
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0]["state"], "CLEARED")
        changes = [row["change_type"] for row in self.repo.alert_history("T1")]
        self.assertEqual(changes, ["CLEARED", "CREATED"])


if __name__ == "__main__":
    unittest.main()
