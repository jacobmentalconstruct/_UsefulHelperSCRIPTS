from __future__ import annotations

from datetime import date, timedelta
import tkinter as tk
from tkinter import messagebox, simpledialog

from domain.payroll import DAY_ORDER
from ui import ApplicationShell, ClientEditorDialog, DayPage, HomePage, MileageSegmentDialog, TotalsPage, apply_dark_theme


class UIOrchestrator:
    def __init__(self, root: tk.Tk, backend):
        self.root = root
        self.backend = backend
        self.shell: ApplicationShell | None = None
        self.home_page: HomePage | None = None
        self.totals_page: TotalsPage | None = None
        self.day_pages: dict[str, DayPage] = {}
        self.snapshot = None
        self.current_page = "home"

    def build_shell(self) -> None:
        apply_dark_theme(self.root)
        self.root.title("Payroll Prototype")
        self.root.geometry("1480x920")
        self.shell = ApplicationShell(self.root)
        self.shell.add_action("Save", self.save)
        self.shell.add_action("Discard", self.discard)
        self.shell.add_action("New Period", self.new_period)
        self.shell.add_nav("home", "Home", lambda: self.show_page("home"))
        self.shell.add_nav("totals", "Totals", lambda: self.show_page("totals"))

        self.home_page = HomePage(
            self.shell.content,
            on_save=self.save,
            on_new_period=self.new_period,
            on_activate_period=self.activate_period,
            on_update_home_base=self.update_home_base,
        )
        self.totals_page = TotalsPage(self.shell.content, on_apply=self.apply_totals)
        self.shell.register_page("home", self.home_page)
        self.shell.register_page("totals", self.totals_page)

        for weekday in DAY_ORDER:
            self.shell.add_nav(weekday, weekday, lambda day=weekday: self.show_page(day))
            page = DayPage(
                self.shell.content,
                weekday=weekday,
                on_add_row=self.add_day_row,
                on_edit_client=self.open_client_editor,
                on_save_row=self.save_day_row,
                on_remove_row=self.remove_day_row,
                on_save_other_task=self.save_other_task,
                on_generate_route=self.generate_route,
                on_add_personal_segment=self.add_personal_segment,
                on_edit_segment=self.edit_segment,
                on_delete_segment=self.delete_segment,
            )
            self.day_pages[weekday] = page
            self.shell.register_page(weekday, page)
        self.show_page("home")

    def show_page(self, page_id: str) -> None:
        self.current_page = page_id
        if self.shell is not None:
            self.shell.show_page(page_id)

    def apply_snapshot(self, snapshot) -> None:
        self.snapshot = snapshot
        if self.shell is None or self.home_page is None or self.totals_page is None:
            return
        self.home_page.apply_snapshot(snapshot)
        self.totals_page.apply_snapshot(snapshot)
        for weekday, page in self.day_pages.items():
            page.apply_snapshot(snapshot.days[weekday])
        self.shell.set_title(f"Payroll Prototype | Period {snapshot.pay_period.start_date.isoformat()}")
        state = "Unsaved" if snapshot.dirty else "Saved"
        self.shell.set_status(f"{state} | Net Pay {snapshot.summary.net_pay:.2f} | Page {self.current_page}")

    def refresh(self) -> None:
        self.apply_snapshot(self.backend.snapshot())

    def save(self) -> None:
        self.backend.save()
        self.refresh()

    def discard(self) -> None:
        if not self.backend.dirty:
            return
        if not messagebox.askyesno("Discard Changes", "Discard all uncommitted changes?"):
            return
        self.backend.discard_uncommitted()
        self.refresh()

    def new_period(self) -> None:
        current = self.backend.get_active_period()
        default_start = (current.start_date + timedelta(days=14)).isoformat()
        entered = simpledialog.askstring("New Pay Period", "Start date (YYYY-MM-DD)", initialvalue=default_start, parent=self.root)
        if not entered:
            return
        try:
            start_date = date.fromisoformat(entered.strip())
        except ValueError:
            messagebox.showerror("Invalid Date", "Use YYYY-MM-DD format.")
            return
        self.backend.create_period(start_date=start_date, copy_from_previous=True)
        self.refresh()

    def activate_period(self, period_id: int) -> None:
        self.backend.activate_period(period_id)
        self.refresh()

    def update_home_base(self, name: str, address: str) -> None:
        self.backend.update_home_base(name=name, address=address)
        self.refresh()

    def apply_totals(self, start_date: str, hourly_rate: str, yto_rate: str, snow_rate: str, owed_amount: str, tax_rate: str) -> None:
        try:
            self.backend.update_totals(
                start_date=date.fromisoformat(start_date.strip()),
                hourly_rate=float(hourly_rate.strip()),
                yto_rate=float(yto_rate.strip()),
                snow_day_multiplier=float(snow_rate.strip()),
                owed_amount=float(owed_amount.strip()),
                tax_rate=float(tax_rate.strip()),
            )
        except ValueError:
            messagebox.showerror("Invalid Value", "Totals values must use valid dates and numbers.")
            return
        self.refresh()

    def add_day_row(self, weekday: str, week_index: int) -> None:
        self.backend.add_day_row(weekday, week_index)
        self.refresh()

    def save_day_row(
        self,
        entry_id: int,
        client_id: int | None,
        route_stop: bool,
        status: str,
        rate_override: float | None,
        comments: str,
    ) -> None:
        self.backend.update_day_row(
            entry_id,
            client_id=client_id,
            route_stop=route_stop,
            status=status,
            rate_override=rate_override,
            comments=comments,
        )
        self.refresh()

    def remove_day_row(self, entry_id: int) -> None:
        self.backend.remove_day_row(entry_id)
        self.refresh()

    def save_other_task(self, weekday: str, week_index: int, label: str, hours: float, notes: str) -> None:
        self.backend.update_other_task(weekday, week_index, label=label, hours=hours, notes=notes)
        self.refresh()

    def generate_route(self, weekday: str, week_index: int) -> None:
        self.backend.generate_route_segments(weekday, week_index)
        self.refresh()

    def open_client_editor(self, entry_id: int, current_client_id: int | None) -> None:
        if self.snapshot is None:
            return
        dialog = ClientEditorDialog(
            self.root,
            clients=list(self.snapshot.clients),
            save_client=self.backend.update_client,
            initial_client_id=current_client_id,
        )
        client_id = dialog.show()
        if client_id is None:
            return
        self.backend.assign_client_to_row(entry_id, client_id)
        self.refresh()

    def add_personal_segment(self, weekday: str, week_index: int) -> None:
        if self.snapshot is None:
            return
        week_snapshot = self.snapshot.days[weekday].weeks[week_index]
        next_sequence = max((segment.sequence for segment in week_snapshot.segments), default=0) + 5
        dialog = MileageSegmentDialog(
            self.root,
            title=f"Add Personal Segment - {weekday} {week_index}",
            initial={"sequence": next_sequence, "segment_type": "personal"},
        )
        payload = dialog.show()
        if payload is None:
            return
        self.backend.insert_personal_segment(weekday, week_index, **payload)
        self.refresh()

    def _find_segment(self, segment_id: int):
        if self.snapshot is None:
            return None
        for day_snapshot in self.snapshot.days.values():
            for week_snapshot in day_snapshot.weeks.values():
                for segment in week_snapshot.segments:
                    if segment.id == segment_id:
                        return segment
        return None

    def edit_segment(self, segment_id: int) -> None:
        segment = self._find_segment(segment_id)
        if segment is None:
            return
        dialog = MileageSegmentDialog(
            self.root,
            title="Edit Mileage Segment",
            initial={
                "sequence": segment.sequence,
                "segment_type": segment.segment_type,
                "from_endpoint": segment.from_endpoint,
                "to_endpoint": segment.to_endpoint,
                "odometer_start": segment.odometer_start,
                "odometer_end": segment.odometer_end,
                "direct_miles": segment.direct_miles,
                "notes": segment.notes,
            },
        )
        payload = dialog.show()
        if payload is None:
            return
        self.backend.update_segment(
            segment_id,
            auto_generated=segment.auto_generated,
            stale=segment.stale,
            **payload,
        )
        self.refresh()

    def delete_segment(self, segment_id: int) -> None:
        if not messagebox.askyesno("Delete Segment", "Delete the selected mileage segment?"):
            return
        self.backend.delete_segment(segment_id)
        self.refresh()

    def confirm_close(self) -> bool | None:
        if not self.backend.dirty:
            return True
        choice = messagebox.askyesnocancel(
            "Unsaved Changes",
            "Save changes before closing?\n\nYes = save and close\nNo = discard and close\nCancel = stay open",
            parent=self.root,
        )
        return choice
