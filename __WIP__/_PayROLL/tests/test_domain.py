from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from domain.payroll import (  # noqa: E402
    ClientRecord,
    DayEntryRecord,
    DayPageSnapshot,
    OtherTaskRecord,
    PayPeriodRecord,
    RenderedDayRow,
    VisitStatus,
    build_day_week_snapshot,
    build_period_summary,
    normalize_status,
    visit_amount,
)


class DomainTests(unittest.TestCase):
    def test_normalize_status_handles_aliases(self) -> None:
        self.assertEqual(normalize_status("skip"), VisitStatus.SKIPPED)
        self.assertEqual(normalize_status("snow day"), VisitStatus.SNOW_DAY)
        self.assertEqual(normalize_status(""), "")

    def test_visit_amount_uses_rate_logic(self) -> None:
        self.assertEqual(visit_amount("Done", 15.0, 0.8), 15.0)
        self.assertEqual(visit_amount("YTO", 15.0, 0.8), 15.0)
        self.assertEqual(visit_amount("Snow_Day", 15.0, 0.8), 12.0)
        self.assertEqual(visit_amount("Skipped", 15.0, 0.8), "SKIP")

    def test_period_summary_rolls_up_numeric_only(self) -> None:
        pay_period = PayPeriodRecord(
            id=1,
            start_date=date(2026, 2, 22),
            hourly_rate=20.0,
            yto_rate=0.0,
            snow_day_multiplier=0.8,
            owed_amount=10.0,
            tax_rate=0.25,
        )
        client = ClientRecord(id=1, name="Client A", default_rate=15.0)
        sunday_w1 = build_day_week_snapshot(
            pay_period,
            "Sunday",
            1,
            rows=[
                RenderedDayRow(
                    entry=DayEntryRecord(id=1, pay_period_id=1, weekday="Sunday", week_index=1, display_order=1, client_id=1, route_stop=True, status="Done"),
                    client=client,
                    effective_rate=15.0,
                    amount=15.0,
                )
            ],
            other_task=OtherTaskRecord(id=1, pay_period_id=1, weekday="Sunday", week_index=1, label="Office", hours=1.0),
            segments=[],
        )
        sunday_w2 = build_day_week_snapshot(
            pay_period,
            "Sunday",
            2,
            rows=[
                RenderedDayRow(
                    entry=DayEntryRecord(id=2, pay_period_id=1, weekday="Sunday", week_index=2, display_order=1, client_id=1, route_stop=True, status="Skipped"),
                    client=client,
                    effective_rate=15.0,
                    amount="SKIP",
                )
            ],
            other_task=OtherTaskRecord(id=2, pay_period_id=1, weekday="Sunday", week_index=2, label="Office", hours=0.0),
            segments=[],
        )
        empty = {}
        for weekday in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"):
            empty[weekday] = DayPageSnapshot(
                weekday=weekday,
                weeks={
                    1: build_day_week_snapshot(
                        pay_period,
                        weekday,
                        1,
                        rows=[],
                        other_task=OtherTaskRecord(id=10, pay_period_id=1, weekday=weekday, week_index=1),
                        segments=[],
                    ),
                    2: build_day_week_snapshot(
                        pay_period,
                        weekday,
                        2,
                        rows=[],
                        other_task=OtherTaskRecord(id=11, pay_period_id=1, weekday=weekday, week_index=2),
                        segments=[],
                    ),
                },
            )
        pages = {"Sunday": DayPageSnapshot(weekday="Sunday", weeks={1: sunday_w1, 2: sunday_w2}), **empty}
        summary = build_period_summary(pay_period, pages)
        self.assertEqual(summary.week_one_total, 35.0)
        self.assertEqual(summary.week_two_total, 0.0)
        self.assertEqual(summary.gross_total, 25.0)
        self.assertEqual(summary.estimated_taxes, 6.25)
        self.assertEqual(summary.net_pay, 18.75)


if __name__ == "__main__":
    unittest.main()
