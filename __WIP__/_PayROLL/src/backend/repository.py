from __future__ import annotations

from datetime import UTC, date, datetime

from domain.payroll import (
    DEFAULT_CLIENT_ROWS_PER_WEEK,
    DEFAULT_HOME_BASE_ADDRESS,
    DEFAULT_HOME_BASE_NAME,
    DAY_ORDER,
    ClientRecord,
    DayEntryRecord,
    MileageSegmentRecord,
    OtherTaskRecord,
    PayPeriodRecord,
)

from .db import Database


def _utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class PayrollRepository:
    def __init__(self, database: Database):
        self.database = database

    def get_setting(self, key: str, default: str = "") -> str:
        row = self.database.query_one(
            "SELECT setting_value FROM app_settings WHERE setting_key = ?",
            (key,),
        )
        if row is None:
            return default
        return str(row["setting_value"])

    def set_setting(self, key: str, value: str) -> None:
        now = _utcnow()
        self.database.execute(
            """
            INSERT INTO app_settings(setting_key, setting_value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(setting_key) DO UPDATE
            SET setting_value = excluded.setting_value,
                updated_at = excluded.updated_at
            """,
            (key, value, now),
        )

    def ensure_default_settings(self) -> None:
        if not self.get_setting("home_base_name"):
            self.set_setting("home_base_name", DEFAULT_HOME_BASE_NAME)
        if not self.get_setting("home_base_address"):
            self.set_setting("home_base_address", DEFAULT_HOME_BASE_ADDRESS)

    def list_clients(self, active_only: bool = False) -> list[ClientRecord]:
        sql = "SELECT * FROM clients"
        if active_only:
            sql += " WHERE active = 1"
        sql += " ORDER BY active DESC, name COLLATE NOCASE"
        return [self._client_from_row(row) for row in self.database.query_all(sql)]

    def get_client(self, client_id: int | None) -> ClientRecord | None:
        if client_id is None:
            return None
        row = self.database.query_one("SELECT * FROM clients WHERE id = ?", (client_id,))
        if row is None:
            return None
        return self._client_from_row(row)

    def save_client(
        self,
        *,
        client_id: int | None,
        name: str,
        default_rate: float,
        address: str,
        phone_number: str,
        notes: str,
        active: bool,
    ) -> ClientRecord:
        now = _utcnow()
        if client_id is None:
            cursor = self.database.execute(
                """
                INSERT INTO clients(name, default_rate, address, phone_number, notes, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (name.strip(), default_rate, address.strip(), phone_number.strip(), notes.strip(), int(active), now, now),
            )
            client_id = int(cursor.lastrowid)
        else:
            self.database.execute(
                """
                UPDATE clients
                SET name = ?, default_rate = ?, address = ?, phone_number = ?, notes = ?, active = ?, updated_at = ?
                WHERE id = ?
                """,
                (name.strip(), default_rate, address.strip(), phone_number.strip(), notes.strip(), int(active), now, client_id),
            )
        client = self.get_client(client_id)
        if client is None:
            raise RuntimeError("Client save failed")
        return client

    def list_pay_periods(self) -> list[PayPeriodRecord]:
        return [
            self._period_from_row(row)
            for row in self.database.query_all(
                "SELECT * FROM pay_periods ORDER BY start_date DESC, id DESC"
            )
        ]

    def get_pay_period(self, pay_period_id: int) -> PayPeriodRecord | None:
        row = self.database.query_one("SELECT * FROM pay_periods WHERE id = ?", (pay_period_id,))
        if row is None:
            return None
        return self._period_from_row(row)

    def get_active_period(self) -> PayPeriodRecord | None:
        row = self.database.query_one(
            "SELECT * FROM pay_periods WHERE status = 'active' ORDER BY start_date DESC, id DESC LIMIT 1"
        )
        if row is None:
            return None
        return self._period_from_row(row)

    def create_pay_period(
        self,
        *,
        start_date: date,
        hourly_rate: float,
        yto_rate: float,
        snow_day_multiplier: float,
        owed_amount: float,
        tax_rate: float,
    ) -> PayPeriodRecord:
        now = _utcnow()
        self.database.execute("UPDATE pay_periods SET status = 'archived', updated_at = ? WHERE status = 'active'", (now,))
        cursor = self.database.execute(
            """
            INSERT INTO pay_periods(start_date, hourly_rate, yto_rate, snow_day_multiplier, owed_amount, tax_rate, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (start_date.isoformat(), hourly_rate, yto_rate, snow_day_multiplier, owed_amount, tax_rate, now, now),
        )
        pay_period_id = int(cursor.lastrowid)
        self._seed_day_entries(pay_period_id)
        period = self.get_pay_period(pay_period_id)
        if period is None:
            raise RuntimeError("Pay period seed failed")
        return period

    def set_active_period(self, pay_period_id: int) -> PayPeriodRecord:
        now = _utcnow()
        self.database.execute("UPDATE pay_periods SET status = 'archived', updated_at = ? WHERE status = 'active'", (now,))
        self.database.execute(
            "UPDATE pay_periods SET status = 'active', updated_at = ? WHERE id = ?",
            (now, pay_period_id),
        )
        period = self.get_pay_period(pay_period_id)
        if period is None:
            raise RuntimeError("Active pay period was not found")
        return period

    def update_pay_period(
        self,
        pay_period_id: int,
        *,
        start_date: date,
        hourly_rate: float,
        yto_rate: float,
        snow_day_multiplier: float,
        owed_amount: float,
        tax_rate: float,
    ) -> PayPeriodRecord:
        now = _utcnow()
        self.database.execute(
            """
            UPDATE pay_periods
            SET start_date = ?, hourly_rate = ?, yto_rate = ?, snow_day_multiplier = ?, owed_amount = ?, tax_rate = ?, updated_at = ?
            WHERE id = ?
            """,
            (start_date.isoformat(), hourly_rate, yto_rate, snow_day_multiplier, owed_amount, tax_rate, now, pay_period_id),
        )
        period = self.get_pay_period(pay_period_id)
        if period is None:
            raise RuntimeError("Pay period update failed")
        return period

    def list_day_entries(self, pay_period_id: int) -> list[DayEntryRecord]:
        return [
            self._day_entry_from_row(row)
            for row in self.database.query_all(
                """
                SELECT * FROM day_entries
                WHERE pay_period_id = ?
                ORDER BY week_index, weekday, display_order, id
                """,
                (pay_period_id,),
            )
        ]

    def get_day_entry(self, entry_id: int) -> DayEntryRecord | None:
        row = self.database.query_one("SELECT * FROM day_entries WHERE id = ?", (entry_id,))
        if row is None:
            return None
        return self._day_entry_from_row(row)

    def add_day_entry(self, pay_period_id: int, weekday: str, week_index: int) -> DayEntryRecord:
        row = self.database.query_one(
            """
            SELECT COALESCE(MAX(display_order), 0) AS max_order
            FROM day_entries
            WHERE pay_period_id = ? AND weekday = ? AND week_index = ?
            """,
            (pay_period_id, weekday, week_index),
        )
        display_order = int(row["max_order"]) + 1
        now = _utcnow()
        cursor = self.database.execute(
            """
            INSERT INTO day_entries(pay_period_id, weekday, week_index, display_order, route_stop, status, comments, created_at, updated_at)
            VALUES (?, ?, ?, ?, 0, '', '', ?, ?)
            """,
            (pay_period_id, weekday, week_index, display_order, now, now),
        )
        entry = self.get_day_entry(int(cursor.lastrowid))
        if entry is None:
            raise RuntimeError("Failed to create day entry")
        return entry

    def update_day_entry(
        self,
        entry_id: int,
        *,
        client_id: int | None,
        route_stop: bool,
        status: str,
        rate_override: float | None,
        comments: str,
    ) -> DayEntryRecord:
        now = _utcnow()
        self.database.execute(
            """
            UPDATE day_entries
            SET client_id = ?, route_stop = ?, status = ?, rate_override = ?, comments = ?, updated_at = ?
            WHERE id = ?
            """,
            (client_id, int(route_stop), status, rate_override, comments, now, entry_id),
        )
        entry = self.get_day_entry(entry_id)
        if entry is None:
            raise RuntimeError("Failed to update day entry")
        return entry

    def delete_day_entry(self, entry_id: int) -> DayEntryRecord | None:
        entry = self.get_day_entry(entry_id)
        if entry is None:
            return None
        self.database.execute("DELETE FROM day_entries WHERE id = ?", (entry_id,))
        return entry

    def reorder_day_entries(self, pay_period_id: int, weekday: str, week_index: int) -> None:
        rows = self.database.query_all(
            """
            SELECT id FROM day_entries
            WHERE pay_period_id = ? AND weekday = ? AND week_index = ?
            ORDER BY display_order, id
            """,
            (pay_period_id, weekday, week_index),
        )
        now = _utcnow()
        for index, row in enumerate(rows, start=1):
            self.database.execute(
                "UPDATE day_entries SET display_order = ?, updated_at = ? WHERE id = ?",
                (index, now, row["id"]),
            )

    def list_other_tasks(self, pay_period_id: int) -> list[OtherTaskRecord]:
        return [
            self._other_task_from_row(row)
            for row in self.database.query_all(
                """
                SELECT * FROM other_task_entries
                WHERE pay_period_id = ?
                ORDER BY week_index, weekday
                """,
                (pay_period_id,),
            )
        ]

    def get_other_task(self, pay_period_id: int, weekday: str, week_index: int) -> OtherTaskRecord:
        row = self.database.query_one(
            """
            SELECT * FROM other_task_entries
            WHERE pay_period_id = ? AND weekday = ? AND week_index = ?
            """,
            (pay_period_id, weekday, week_index),
        )
        if row is None:
            raise RuntimeError("Other task row is missing")
        return self._other_task_from_row(row)

    def update_other_task(
        self,
        pay_period_id: int,
        weekday: str,
        week_index: int,
        *,
        label: str,
        hours: float,
        notes: str,
    ) -> OtherTaskRecord:
        now = _utcnow()
        self.database.execute(
            """
            UPDATE other_task_entries
            SET label = ?, hours = ?, notes = ?, updated_at = ?
            WHERE pay_period_id = ? AND weekday = ? AND week_index = ?
            """,
            (label.strip(), hours, notes.strip(), now, pay_period_id, weekday, week_index),
        )
        return self.get_other_task(pay_period_id, weekday, week_index)

    def list_segments(self, pay_period_id: int) -> list[MileageSegmentRecord]:
        return [
            self._segment_from_row(row)
            for row in self.database.query_all(
                """
                SELECT * FROM mileage_segments
                WHERE pay_period_id = ?
                ORDER BY week_index, weekday, sequence, id
                """,
                (pay_period_id,),
            )
        ]

    def list_segments_for_year(self, year: int) -> list[MileageSegmentRecord]:
        return [
            self._segment_from_row(row)
            for row in self.database.query_all(
                """
                SELECT mileage_segments.*
                FROM mileage_segments
                INNER JOIN pay_periods ON pay_periods.id = mileage_segments.pay_period_id
                WHERE substr(pay_periods.start_date, 1, 4) = ?
                ORDER BY pay_periods.start_date, mileage_segments.week_index, mileage_segments.weekday, mileage_segments.sequence
                """,
                (str(year),),
            )
        ]

    def list_segments_for_day_week(
        self,
        pay_period_id: int,
        weekday: str,
        week_index: int,
    ) -> list[MileageSegmentRecord]:
        return [
            self._segment_from_row(row)
            for row in self.database.query_all(
                """
                SELECT * FROM mileage_segments
                WHERE pay_period_id = ? AND weekday = ? AND week_index = ?
                ORDER BY sequence, id
                """,
                (pay_period_id, weekday, week_index),
            )
        ]

    def replace_auto_segments(
        self,
        pay_period_id: int,
        weekday: str,
        week_index: int,
        segments: list[tuple[int, str, str, str]],
    ) -> None:
        self.database.execute(
            """
            DELETE FROM mileage_segments
            WHERE pay_period_id = ? AND weekday = ? AND week_index = ? AND auto_generated = 1
            """,
            (pay_period_id, weekday, week_index),
        )
        now = _utcnow()
        for sequence, segment_type, from_endpoint, to_endpoint in segments:
            self.database.execute(
                """
                INSERT INTO mileage_segments(
                    pay_period_id, weekday, week_index, sequence, segment_type, from_endpoint, to_endpoint,
                    notes, auto_generated, stale, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, '', 1, 0, ?, ?)
                """,
                (pay_period_id, weekday, week_index, sequence, segment_type, from_endpoint, to_endpoint, now, now),
            )
        self.clear_segments_stale(pay_period_id, weekday, week_index)

    def insert_segment(
        self,
        *,
        pay_period_id: int,
        weekday: str,
        week_index: int,
        sequence: int,
        segment_type: str,
        from_endpoint: str,
        to_endpoint: str,
        odometer_start: float | None,
        odometer_end: float | None,
        direct_miles: float | None,
        notes: str,
        auto_generated: bool,
        stale: bool,
    ) -> MileageSegmentRecord:
        now = _utcnow()
        cursor = self.database.execute(
            """
            INSERT INTO mileage_segments(
                pay_period_id, weekday, week_index, sequence, segment_type, from_endpoint, to_endpoint,
                odometer_start, odometer_end, direct_miles, notes, auto_generated, stale, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pay_period_id,
                weekday,
                week_index,
                sequence,
                segment_type,
                from_endpoint.strip(),
                to_endpoint.strip(),
                odometer_start,
                odometer_end,
                direct_miles,
                notes.strip(),
                int(auto_generated),
                int(stale),
                now,
                now,
            ),
        )
        segment = self.get_segment(int(cursor.lastrowid))
        if segment is None:
            raise RuntimeError("Failed to create mileage segment")
        return segment

    def get_segment(self, segment_id: int) -> MileageSegmentRecord | None:
        row = self.database.query_one("SELECT * FROM mileage_segments WHERE id = ?", (segment_id,))
        if row is None:
            return None
        return self._segment_from_row(row)

    def update_segment(
        self,
        segment_id: int,
        *,
        sequence: int,
        segment_type: str,
        from_endpoint: str,
        to_endpoint: str,
        odometer_start: float | None,
        odometer_end: float | None,
        direct_miles: float | None,
        notes: str,
        auto_generated: bool,
        stale: bool,
    ) -> MileageSegmentRecord:
        now = _utcnow()
        self.database.execute(
            """
            UPDATE mileage_segments
            SET sequence = ?, segment_type = ?, from_endpoint = ?, to_endpoint = ?,
                odometer_start = ?, odometer_end = ?, direct_miles = ?, notes = ?,
                auto_generated = ?, stale = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                sequence,
                segment_type,
                from_endpoint.strip(),
                to_endpoint.strip(),
                odometer_start,
                odometer_end,
                direct_miles,
                notes.strip(),
                int(auto_generated),
                int(stale),
                now,
                segment_id,
            ),
        )
        segment = self.get_segment(segment_id)
        if segment is None:
            raise RuntimeError("Failed to update mileage segment")
        return segment

    def delete_segment(self, segment_id: int) -> MileageSegmentRecord | None:
        segment = self.get_segment(segment_id)
        if segment is None:
            return None
        self.database.execute("DELETE FROM mileage_segments WHERE id = ?", (segment_id,))
        return segment

    def mark_segments_stale(self, pay_period_id: int, weekday: str, week_index: int) -> None:
        now = _utcnow()
        self.database.execute(
            """
            UPDATE mileage_segments
            SET stale = 1, updated_at = ?
            WHERE pay_period_id = ? AND weekday = ? AND week_index = ?
            """,
            (now, pay_period_id, weekday, week_index),
        )

    def clear_segments_stale(self, pay_period_id: int, weekday: str, week_index: int) -> None:
        now = _utcnow()
        self.database.execute(
            """
            UPDATE mileage_segments
            SET stale = 0, updated_at = ?
            WHERE pay_period_id = ? AND weekday = ? AND week_index = ?
            """,
            (now, pay_period_id, weekday, week_index),
        )

    def _seed_day_entries(self, pay_period_id: int) -> None:
        now = _utcnow()
        for week_index in (1, 2):
            for weekday in DAY_ORDER:
                for display_order in range(1, DEFAULT_CLIENT_ROWS_PER_WEEK + 1):
                    self.database.execute(
                        """
                        INSERT INTO day_entries(
                            pay_period_id, weekday, week_index, display_order, client_id, route_stop, status, rate_override, comments, created_at, updated_at
                        )
                        VALUES (?, ?, ?, ?, NULL, 0, '', NULL, '', ?, ?)
                        """,
                        (pay_period_id, weekday, week_index, display_order, now, now),
                    )
                self.database.execute(
                    """
                    INSERT INTO other_task_entries(pay_period_id, weekday, week_index, label, hours, notes, created_at, updated_at)
                    VALUES (?, ?, ?, 'Office Work', 0, '', ?, ?)
                    """,
                    (pay_period_id, weekday, week_index, now, now),
                )

    @staticmethod
    def _client_from_row(row) -> ClientRecord:
        return ClientRecord(
            id=int(row["id"]),
            name=str(row["name"]),
            default_rate=float(row["default_rate"]),
            address=str(row["address"]),
            phone_number=str(row["phone_number"]),
            notes=str(row["notes"]),
            active=bool(row["active"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _period_from_row(row) -> PayPeriodRecord:
        return PayPeriodRecord(
            id=int(row["id"]),
            start_date=date.fromisoformat(str(row["start_date"])),
            hourly_rate=float(row["hourly_rate"]),
            yto_rate=float(row["yto_rate"]),
            snow_day_multiplier=float(row["snow_day_multiplier"]),
            owed_amount=float(row["owed_amount"]),
            tax_rate=float(row["tax_rate"]),
            status=str(row["status"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _day_entry_from_row(row) -> DayEntryRecord:
        rate_override = row["rate_override"]
        return DayEntryRecord(
            id=int(row["id"]),
            pay_period_id=int(row["pay_period_id"]),
            weekday=str(row["weekday"]),
            week_index=int(row["week_index"]),
            display_order=int(row["display_order"]),
            client_id=int(row["client_id"]) if row["client_id"] is not None else None,
            route_stop=bool(row["route_stop"]),
            status=str(row["status"]),
            rate_override=float(rate_override) if rate_override is not None else None,
            comments=str(row["comments"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _other_task_from_row(row) -> OtherTaskRecord:
        return OtherTaskRecord(
            id=int(row["id"]),
            pay_period_id=int(row["pay_period_id"]),
            weekday=str(row["weekday"]),
            week_index=int(row["week_index"]),
            label=str(row["label"]),
            hours=float(row["hours"]),
            notes=str(row["notes"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _segment_from_row(row) -> MileageSegmentRecord:
        return MileageSegmentRecord(
            id=int(row["id"]),
            pay_period_id=int(row["pay_period_id"]),
            weekday=str(row["weekday"]),
            week_index=int(row["week_index"]),
            sequence=int(row["sequence"]),
            segment_type=str(row["segment_type"]),
            from_endpoint=str(row["from_endpoint"]),
            to_endpoint=str(row["to_endpoint"]),
            odometer_start=float(row["odometer_start"]) if row["odometer_start"] is not None else None,
            odometer_end=float(row["odometer_end"]) if row["odometer_end"] is not None else None,
            direct_miles=float(row["direct_miles"]) if row["direct_miles"] is not None else None,
            notes=str(row["notes"]),
            auto_generated=bool(row["auto_generated"]),
            stale=bool(row["stale"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
