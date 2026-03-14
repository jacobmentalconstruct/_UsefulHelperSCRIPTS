from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from backend import Database, PayrollRepository, PayrollService, RouteService
from domain.payroll import DAY_ORDER, TAX_RATE_DEFAULT, WEEK_INDEXES, AppSnapshot, PayPeriodRecord, period_start_for_date


class BackendOrchestrator:
    def __init__(self):
        self.database: Database | None = None
        self.repository: PayrollRepository | None = None
        self.payroll_service: PayrollService | None = None
        self.route_service: RouteService | None = None
        self.current_period_id: int | None = None
        self.dirty = False
        self.database_path: Path | None = None

    def create_or_open_database(self, path: Path) -> None:
        self.database_path = Path(path)
        self.database = Database(self.database_path)
        self.database.initialize()
        self.repository = PayrollRepository(self.database)
        self.repository.ensure_default_settings()
        active = self.repository.get_active_period()
        if active is None:
            active = self.repository.create_pay_period(
                start_date=period_start_for_date(date.today()),
                hourly_rate=20.0,
                yto_rate=0.0,
                snow_day_multiplier=0.8,
                owed_amount=0.0,
                tax_rate=TAX_RATE_DEFAULT,
            )
            self.database.commit()
        else:
            self.database.commit()
        self.payroll_service = PayrollService(self.repository)
        self.route_service = RouteService(self.repository)
        self.current_period_id = active.id
        self.dirty = False

    def _require_repository(self) -> PayrollRepository:
        if self.repository is None:
            raise RuntimeError("Backend has not been initialized")
        return self.repository

    def _require_database(self) -> Database:
        if self.database is None:
            raise RuntimeError("Database has not been initialized")
        return self.database

    def _require_payroll_service(self) -> PayrollService:
        if self.payroll_service is None:
            raise RuntimeError("Payroll service has not been initialized")
        return self.payroll_service

    def _require_route_service(self) -> RouteService:
        if self.route_service is None:
            raise RuntimeError("Route service has not been initialized")
        return self.route_service

    def _active_period(self) -> PayPeriodRecord:
        repository = self._require_repository()
        period = repository.get_pay_period(self.current_period_id or 0)
        if period is None:
            raise RuntimeError("No active pay period is available")
        return period

    def get_active_period(self) -> PayPeriodRecord:
        return self._active_period()

    def list_periods(self) -> list[PayPeriodRecord]:
        return self._require_repository().list_pay_periods()

    def create_period(self, start_date: date | None = None, copy_from_previous: bool = False) -> PayPeriodRecord:
        current = self._active_period()
        next_start = start_date or (current.start_date + timedelta(days=14))
        period = self._require_repository().create_pay_period(
            start_date=next_start,
            hourly_rate=current.hourly_rate if copy_from_previous else 20.0,
            yto_rate=current.yto_rate if copy_from_previous else 0.0,
            snow_day_multiplier=current.snow_day_multiplier if copy_from_previous else 0.8,
            owed_amount=0.0,
            tax_rate=current.tax_rate if copy_from_previous else TAX_RATE_DEFAULT,
        )
        self.current_period_id = period.id
        self.dirty = True
        return period

    def activate_period(self, pay_period_id: int) -> PayPeriodRecord:
        period = self._require_repository().set_active_period(pay_period_id)
        self.current_period_id = period.id
        self.dirty = True
        return period

    def update_totals(
        self,
        *,
        start_date: date,
        hourly_rate: float,
        yto_rate: float,
        snow_day_multiplier: float,
        owed_amount: float,
        tax_rate: float,
    ) -> PayPeriodRecord:
        period = self._require_repository().update_pay_period(
            self._active_period().id or 0,
            start_date=start_date,
            hourly_rate=hourly_rate,
            yto_rate=yto_rate,
            snow_day_multiplier=snow_day_multiplier,
            owed_amount=owed_amount,
            tax_rate=tax_rate,
        )
        self.dirty = True
        return period

    def update_client(
        self,
        *,
        client_id: int | None,
        name: str,
        default_rate: float,
        address: str,
        phone_number: str,
        notes: str,
        active: bool,
    ):
        client = self._require_repository().save_client(
            client_id=client_id,
            name=name,
            default_rate=default_rate,
            address=address,
            phone_number=phone_number,
            notes=notes,
            active=active,
        )
        self.dirty = True
        return client

    def add_day_row(self, weekday: str, week_index: int):
        row = self._require_repository().add_day_entry(self._active_period().id or 0, weekday, week_index)
        self._require_repository().mark_segments_stale(self._active_period().id or 0, weekday, week_index)
        self.dirty = True
        return row

    def update_day_row(
        self,
        entry_id: int,
        *,
        client_id: int | None,
        route_stop: bool,
        status: str,
        rate_override: float | None,
        comments: str,
    ):
        entry = self._require_repository().update_day_entry(
            entry_id,
            client_id=client_id,
            route_stop=route_stop,
            status=status,
            rate_override=rate_override,
            comments=comments,
        )
        self._require_repository().mark_segments_stale(entry.pay_period_id, entry.weekday, entry.week_index)
        self.dirty = True
        return entry

    def assign_client_to_row(self, entry_id: int, client_id: int | None):
        entry = self._require_repository().get_day_entry(entry_id)
        if entry is None:
            raise RuntimeError("Day entry was not found")
        return self.update_day_row(
            entry_id,
            client_id=client_id,
            route_stop=entry.route_stop,
            status=str(entry.status),
            rate_override=entry.rate_override,
            comments=entry.comments,
        )

    def remove_day_row(self, entry_id: int):
        entry = self._require_repository().delete_day_entry(entry_id)
        if entry is not None:
            self._require_repository().reorder_day_entries(entry.pay_period_id, entry.weekday, entry.week_index)
            self._require_repository().mark_segments_stale(entry.pay_period_id, entry.weekday, entry.week_index)
            self.dirty = True
        return entry

    def update_other_task(self, weekday: str, week_index: int, *, label: str, hours: float, notes: str = ""):
        other_task = self._require_repository().update_other_task(
            self._active_period().id or 0,
            weekday,
            week_index,
            label=label,
            hours=hours,
            notes=notes,
        )
        self.dirty = True
        return other_task

    def update_home_base(self, *, name: str, address: str) -> None:
        repository = self._require_repository()
        repository.set_setting("home_base_name", name.strip())
        repository.set_setting("home_base_address", address.strip())
        period_id = self._active_period().id or 0
        for weekday in DAY_ORDER:
            for week_index in WEEK_INDEXES:
                repository.mark_segments_stale(period_id, weekday, week_index)
        self.dirty = True

    def generate_route_segments(self, weekday: str, week_index: int) -> None:
        self._require_route_service().generate_segments(self._active_period().id or 0, weekday, week_index)
        self.dirty = True

    def insert_personal_segment(
        self,
        weekday: str,
        week_index: int,
        *,
        sequence: int,
        from_endpoint: str,
        to_endpoint: str,
        odometer_start: float | None,
        odometer_end: float | None,
        direct_miles: float | None,
        notes: str,
    ):
        segment = self._require_repository().insert_segment(
            pay_period_id=self._active_period().id or 0,
            weekday=weekday,
            week_index=week_index,
            sequence=sequence,
            segment_type="personal",
            from_endpoint=from_endpoint,
            to_endpoint=to_endpoint,
            odometer_start=odometer_start,
            odometer_end=odometer_end,
            direct_miles=direct_miles,
            notes=notes,
            auto_generated=False,
            stale=False,
        )
        self.dirty = True
        return segment

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
    ):
        segment = self._require_repository().update_segment(
            segment_id,
            sequence=sequence,
            segment_type=segment_type,
            from_endpoint=from_endpoint,
            to_endpoint=to_endpoint,
            odometer_start=odometer_start,
            odometer_end=odometer_end,
            direct_miles=direct_miles,
            notes=notes,
            auto_generated=auto_generated,
            stale=stale,
        )
        self.dirty = True
        return segment

    def delete_segment(self, segment_id: int):
        segment = self._require_repository().delete_segment(segment_id)
        if segment is not None:
            self.dirty = True
        return segment

    def snapshot(self, period_id: int | None = None) -> AppSnapshot:
        if period_id is not None:
            self.current_period_id = period_id
        period = self._active_period()
        return self._require_payroll_service().build_snapshot(period, self.dirty)

    def save(self) -> None:
        self._require_database().commit()
        self.dirty = False

    def discard_uncommitted(self) -> None:
        self._require_database().rollback()
        self.dirty = False

    def close(self, save_changes: bool = True) -> None:
        if self.database is None:
            return
        if save_changes and self.dirty:
            self.database.commit()
        elif not save_changes and self.dirty:
            self.database.rollback()
        self.database.close()
        self.database = None

    def health_snapshot(self) -> dict[str, object]:
        return {
            "database_path": str(self.database_path) if self.database_path else "",
            "active_period_id": self.current_period_id,
            "dirty": self.dirty,
        }
