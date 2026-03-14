from __future__ import annotations

import sys
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from orchestration.backend import BackendOrchestrator  # noqa: E402


class BackendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "payroll.sqlite3"
        self.backend = BackendOrchestrator()
        self.backend.create_or_open_database(self.db_path)

    def tearDown(self) -> None:
        self.backend.close(save_changes=False)
        self.temp_dir.cleanup()

    def test_default_period_and_client_flow(self) -> None:
        snapshot = self.backend.snapshot()
        self.assertIsNotNone(snapshot.pay_period.id)
        client = self.backend.update_client(
            client_id=None,
            name="Acme Yard",
            default_rate=18.5,
            address="123 Main",
            phone_number="555-0100",
            notes="Gate code 42",
            active=True,
        )
        row = snapshot.days["Sunday"].weeks[1].rows[0].entry
        self.backend.update_day_row(
            row.id,
            client_id=client.id,
            route_stop=True,
            status="Done",
            rate_override=None,
            comments="Completed",
        )
        updated = self.backend.snapshot()
        sunday_row = updated.days["Sunday"].weeks[1].rows[0]
        self.assertEqual(sunday_row.client.name, "Acme Yard")
        self.assertEqual(sunday_row.amount, 18.5)
        self.assertTrue(self.backend.dirty)

    def test_route_generation_and_stale_marking(self) -> None:
        sunday_rows = self.backend.snapshot().days["Sunday"].weeks[1].rows[:2]
        first = self.backend.update_client(
            client_id=None,
            name="First Yard",
            default_rate=10.0,
            address="One",
            phone_number="",
            notes="",
            active=True,
        )
        second = self.backend.update_client(
            client_id=None,
            name="Second Yard",
            default_rate=12.0,
            address="Two",
            phone_number="",
            notes="",
            active=True,
        )
        self.backend.update_day_row(sunday_rows[0].entry.id, client_id=first.id, route_stop=True, status="Done", rate_override=None, comments="")
        self.backend.update_day_row(sunday_rows[1].entry.id, client_id=second.id, route_stop=True, status="Done", rate_override=None, comments="")
        self.backend.generate_route_segments("Sunday", 1)
        snapshot = self.backend.snapshot()
        segments = snapshot.days["Sunday"].weeks[1].segments
        self.assertEqual([segment.segment_type for segment in segments], ["commute_start", "work", "commute_end"])
        self.assertEqual(segments[1].from_endpoint, "First Yard")
        self.assertEqual(segments[1].to_endpoint, "Second Yard")

        self.backend.update_day_row(sunday_rows[1].entry.id, client_id=second.id, route_stop=False, status="Done", rate_override=None, comments="")
        stale_snapshot = self.backend.snapshot()
        self.assertTrue(stale_snapshot.days["Sunday"].weeks[1].stale_route)

    def test_save_and_reopen_persists_state(self) -> None:
        client = self.backend.update_client(
            client_id=None,
            name="Persisted Yard",
            default_rate=22.0,
            address="Somewhere",
            phone_number="555-1111",
            notes="Persistence test",
            active=True,
        )
        self.backend.save()
        self.assertFalse(self.backend.dirty)
        self.backend.close(save_changes=True)

        reopened = BackendOrchestrator()
        reopened.create_or_open_database(self.db_path)
        try:
            snapshot = reopened.snapshot()
            names = [item.name for item in snapshot.clients]
            self.assertIn(client.name, names)
        finally:
            reopened.close(save_changes=False)


if __name__ == "__main__":
    unittest.main()
