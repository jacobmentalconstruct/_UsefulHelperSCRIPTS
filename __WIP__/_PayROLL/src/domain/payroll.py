from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from typing import Dict, Iterable, Mapping


class VisitStatus(StrEnum):
    DONE = "Done"
    YTO = "YTO"
    SKIPPED = "Skipped"
    OFF = "Off"
    SNOW_DAY = "Snow_Day"


STATUS_ALIASES: Dict[str, VisitStatus] = {
    "done": VisitStatus.DONE,
    "yto": VisitStatus.YTO,
    "skip": VisitStatus.SKIPPED,
    "skipped": VisitStatus.SKIPPED,
    "off": VisitStatus.OFF,
    "snow_day": VisitStatus.SNOW_DAY,
    "snow day": VisitStatus.SNOW_DAY,
    "bad weather": VisitStatus.SNOW_DAY,
}

DAY_ORDER = (
    "Sunday",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
)
DAY_INDEX = {name: idx for idx, name in enumerate(DAY_ORDER)}
WEEK_INDEXES = (1, 2)
WEEK_LABELS = {1: "Week 1", 2: "Week 2"}
SEGMENT_TYPES = ("commute_start", "work", "commute_end", "personal")
DEFAULT_HOME_BASE_NAME = "Home Base"
DEFAULT_HOME_BASE_ADDRESS = ""
DEFAULT_CLIENT_ROWS_PER_WEEK = 4
TAX_RATE_DEFAULT = 0.33


def normalize_status(value: str | VisitStatus) -> VisitStatus | str:
    if isinstance(value, VisitStatus):
        return value
    cleaned = value.strip()
    if not cleaned:
        return ""
    return STATUS_ALIASES.get(cleaned.lower(), cleaned)


def period_start_for_date(target: date) -> date:
    days_since_sunday = (target.weekday() + 1) % 7
    return target - timedelta(days=days_since_sunday)


def day_date_for_period(pay_period_start: date, weekday: str, week_index: int) -> date:
    return pay_period_start + timedelta(days=DAY_INDEX[weekday] + ((week_index - 1) * 7))


def format_currency(value: float) -> str:
    return f"${value:,.2f}"


def effective_rate(default_rate: float, override_rate: float | None) -> float:
    if override_rate is None:
        return default_rate
    return override_rate


def visit_amount(status: VisitStatus | str, rate: float, snow_day_multiplier: float) -> float | str:
    normalized = normalize_status(status)
    if normalized == VisitStatus.SNOW_DAY:
        return round(rate * snow_day_multiplier, 2)
    if normalized in {VisitStatus.DONE, VisitStatus.YTO}:
        return round(rate, 2)
    if normalized == VisitStatus.SKIPPED:
        return "SKIP"
    if normalized == VisitStatus.OFF:
        return "n/a"
    return ""


def other_task_amount(hours: float, hourly_rate: float) -> float | str:
    if hours <= 0:
        return "n/a"
    return round(hours * hourly_rate, 2)


def numeric_total(values: Iterable[float | str]) -> float:
    total = 0.0
    for value in values:
        if isinstance(value, (int, float)):
            total += float(value)
    return round(total, 2)


def mileage_value(direct_miles: float | None, odometer_start: float | None, odometer_end: float | None) -> float:
    if direct_miles is not None:
        return round(direct_miles, 2)
    if odometer_start is not None and odometer_end is not None:
        return round(max(0.0, odometer_end - odometer_start), 2)
    return 0.0


@dataclass(frozen=True)
class ClientRecord:
    id: int | None
    name: str
    default_rate: float
    address: str = ""
    phone_number: str = ""
    notes: str = ""
    active: bool = True
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class PayPeriodRecord:
    id: int | None
    start_date: date
    hourly_rate: float
    yto_rate: float
    snow_day_multiplier: float
    owed_amount: float
    tax_rate: float = TAX_RATE_DEFAULT
    status: str = "active"
    created_at: str | None = None
    updated_at: str | None = None

    def week_start(self, week_index: int) -> date:
        return self.start_date + timedelta(days=(week_index - 1) * 7)

    def day_date(self, weekday: str, week_index: int) -> date:
        return day_date_for_period(self.start_date, weekday, week_index)


@dataclass(frozen=True)
class DayEntryRecord:
    id: int | None
    pay_period_id: int
    weekday: str
    week_index: int
    display_order: int
    client_id: int | None = None
    route_stop: bool = False
    status: VisitStatus | str = ""
    rate_override: float | None = None
    comments: str = ""
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class OtherTaskRecord:
    id: int | None
    pay_period_id: int
    weekday: str
    week_index: int
    label: str = "Office Work"
    hours: float = 0.0
    notes: str = ""
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class MileageSegmentRecord:
    id: int | None
    pay_period_id: int
    weekday: str
    week_index: int
    sequence: int
    segment_type: str
    from_endpoint: str
    to_endpoint: str
    odometer_start: float | None = None
    odometer_end: float | None = None
    direct_miles: float | None = None
    notes: str = ""
    auto_generated: bool = True
    stale: bool = False
    created_at: str | None = None
    updated_at: str | None = None

    @property
    def miles(self) -> float:
        return mileage_value(self.direct_miles, self.odometer_start, self.odometer_end)


@dataclass(frozen=True)
class RenderedDayRow:
    entry: DayEntryRecord
    client: ClientRecord | None
    effective_rate: float
    amount: float | str


@dataclass(frozen=True)
class DayWeekSnapshot:
    weekday: str
    week_index: int
    work_date: date
    rows: tuple[RenderedDayRow, ...]
    other_task: OtherTaskRecord
    other_task_amount: float | str
    segments: tuple[MileageSegmentRecord, ...]
    stale_route: bool
    total_pay: float
    mileage_total: float


@dataclass(frozen=True)
class DayPageSnapshot:
    weekday: str
    weeks: Mapping[int, DayWeekSnapshot]


@dataclass(frozen=True)
class PeriodSummary:
    week_one_total: float
    week_two_total: float
    gross_total: float
    estimated_taxes: float
    net_pay: float
    day_totals: Mapping[str, float]


@dataclass(frozen=True)
class YearlyMileageSummary:
    year: int
    by_type: Mapping[str, float]
    by_client: Mapping[str, float]
    total: float


@dataclass(frozen=True)
class AppSnapshot:
    pay_period: PayPeriodRecord
    days: Mapping[str, DayPageSnapshot]
    clients: tuple[ClientRecord, ...]
    history: tuple[PayPeriodRecord, ...]
    summary: PeriodSummary
    yearly_mileage: YearlyMileageSummary
    home_base_name: str
    home_base_address: str
    dirty: bool


def build_day_week_snapshot(
    pay_period: PayPeriodRecord,
    weekday: str,
    week_index: int,
    rows: Iterable[RenderedDayRow],
    other_task: OtherTaskRecord,
    segments: Iterable[MileageSegmentRecord],
) -> DayWeekSnapshot:
    row_list = tuple(rows)
    segment_list = tuple(sorted(segments, key=lambda item: item.sequence))
    pay_values = [item.amount for item in row_list]
    other_amount = other_task_amount(other_task.hours, pay_period.hourly_rate)
    total_pay = numeric_total([*pay_values, other_amount])
    mileage_total = numeric_total(segment.miles for segment in segment_list)
    stale_route = any(segment.stale for segment in segment_list)
    return DayWeekSnapshot(
        weekday=weekday,
        week_index=week_index,
        work_date=pay_period.day_date(weekday, week_index),
        rows=row_list,
        other_task=other_task,
        other_task_amount=other_amount,
        segments=segment_list,
        stale_route=stale_route,
        total_pay=total_pay,
        mileage_total=mileage_total,
    )


def build_period_summary(
    pay_period: PayPeriodRecord,
    days: Mapping[str, DayPageSnapshot],
) -> PeriodSummary:
    day_totals: dict[str, float] = {}
    week_one_total = 0.0
    week_two_total = 0.0
    for weekday in DAY_ORDER:
        day_snapshot = days[weekday]
        day_total = 0.0
        for week_index in WEEK_INDEXES:
            week_total = day_snapshot.weeks[week_index].total_pay
            day_total += week_total
            if week_index == 1:
                week_one_total += week_total
            else:
                week_two_total += week_total
        day_totals[weekday] = round(day_total, 2)
    gross_total = round((week_one_total + week_two_total) - pay_period.owed_amount, 2)
    estimated_taxes = round(gross_total * pay_period.tax_rate, 2)
    net_pay = round(gross_total - estimated_taxes, 2)
    return PeriodSummary(
        week_one_total=round(week_one_total, 2),
        week_two_total=round(week_two_total, 2),
        gross_total=gross_total,
        estimated_taxes=estimated_taxes,
        net_pay=net_pay,
        day_totals=day_totals,
    )


def build_yearly_mileage_summary(
    year: int,
    segments: Iterable[MileageSegmentRecord],
    client_names: Iterable[str],
) -> YearlyMileageSummary:
    client_name_set = set(client_names)
    by_type = {segment_type: 0.0 for segment_type in SEGMENT_TYPES}
    by_client: dict[str, float] = {}
    total = 0.0
    for segment in segments:
        miles = segment.miles
        by_type[segment.segment_type] = round(by_type.get(segment.segment_type, 0.0) + miles, 2)
        total += miles
        if segment.segment_type in {"commute_start", "work"} and segment.to_endpoint in client_name_set:
            by_client[segment.to_endpoint] = round(by_client.get(segment.to_endpoint, 0.0) + miles, 2)
    return YearlyMileageSummary(
        year=year,
        by_type=by_type,
        by_client=dict(sorted(by_client.items(), key=lambda item: (-item[1], item[0]))),
        total=round(total, 2),
    )
