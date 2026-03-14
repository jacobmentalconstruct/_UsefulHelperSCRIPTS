from __future__ import annotations

from collections import defaultdict

from domain.payroll import (
    DAY_ORDER,
    WEEK_INDEXES,
    AppSnapshot,
    DayPageSnapshot,
    MileageSegmentRecord,
    PayPeriodRecord,
    RenderedDayRow,
    build_day_week_snapshot,
    build_period_summary,
    build_yearly_mileage_summary,
    effective_rate,
    visit_amount,
)

from .repository import PayrollRepository


class PayrollService:
    def __init__(self, repository: PayrollRepository):
        self.repository = repository

    def build_snapshot(self, pay_period: PayPeriodRecord, dirty: bool) -> AppSnapshot:
        clients = tuple(self.repository.list_clients())
        client_map = {client.id: client for client in clients}
        day_entries = self.repository.list_day_entries(pay_period.id or 0)
        other_tasks = {
            (item.weekday, item.week_index): item
            for item in self.repository.list_other_tasks(pay_period.id or 0)
        }
        segments_by_day_week: dict[tuple[str, int], list[MileageSegmentRecord]] = defaultdict(list)
        for segment in self.repository.list_segments(pay_period.id or 0):
            segments_by_day_week[(segment.weekday, segment.week_index)].append(segment)

        rows_by_day_week: dict[tuple[str, int], list[RenderedDayRow]] = defaultdict(list)
        for entry in sorted(day_entries, key=lambda item: (item.week_index, item.weekday, item.display_order)):
            client = client_map.get(entry.client_id)
            row_rate = effective_rate(client.default_rate if client else 0.0, entry.rate_override)
            row_amount = visit_amount(entry.status, row_rate, pay_period.snow_day_multiplier)
            rows_by_day_week[(entry.weekday, entry.week_index)].append(
                RenderedDayRow(entry=entry, client=client, effective_rate=row_rate, amount=row_amount)
            )

        day_pages: dict[str, DayPageSnapshot] = {}
        for weekday in DAY_ORDER:
            weeks = {}
            for week_index in WEEK_INDEXES:
                weeks[week_index] = build_day_week_snapshot(
                    pay_period=pay_period,
                    weekday=weekday,
                    week_index=week_index,
                    rows=rows_by_day_week[(weekday, week_index)],
                    other_task=other_tasks[(weekday, week_index)],
                    segments=segments_by_day_week[(weekday, week_index)],
                )
            day_pages[weekday] = DayPageSnapshot(weekday=weekday, weeks=weeks)

        summary = build_period_summary(pay_period, day_pages)
        history = tuple(self.repository.list_pay_periods())
        yearly_segments = self.repository.list_segments_for_year(pay_period.start_date.year)
        yearly_mileage = build_yearly_mileage_summary(
            year=pay_period.start_date.year,
            segments=yearly_segments,
            client_names=[client.name for client in clients],
        )
        return AppSnapshot(
            pay_period=pay_period,
            days=day_pages,
            clients=clients,
            history=history,
            summary=summary,
            yearly_mileage=yearly_mileage,
            home_base_name=self.repository.get_setting("home_base_name"),
            home_base_address=self.repository.get_setting("home_base_address"),
            dirty=dirty,
        )


class RouteService:
    def __init__(self, repository: PayrollRepository):
        self.repository = repository

    def generate_segments(self, pay_period_id: int, weekday: str, week_index: int) -> None:
        home_base_name = self.repository.get_setting("home_base_name")
        client_map = {client.id: client for client in self.repository.list_clients()}
        rows = [
            row
            for row in self.repository.list_day_entries(pay_period_id)
            if row.weekday == weekday and row.week_index == week_index and row.route_stop and row.client_id
        ]
        rows.sort(key=lambda item: item.display_order)
        stops = [client_map[item.client_id].name for item in rows if item.client_id in client_map]
        segments: list[tuple[int, str, str, str]] = []
        if stops:
            sequence = 10
            segments.append((sequence, "commute_start", home_base_name, stops[0]))
            sequence += 10
            for origin, destination in zip(stops, stops[1:]):
                segments.append((sequence, "work", origin, destination))
                sequence += 10
            segments.append((sequence, "commute_end", stops[-1], home_base_name))
        self.repository.replace_auto_segments(pay_period_id, weekday, week_index, segments)
