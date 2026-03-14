from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from domain.payroll import DAY_ORDER, WEEK_INDEXES, format_currency


def _parse_float(value: str) -> float | None:
    stripped = value.strip()
    if not stripped:
        return None
    return float(stripped)


class ScrollableFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, style="App.TFrame")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, highlightthickness=0, bg="#15191f")
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas, style="App.TFrame")
        self.inner.bind(
            "<Configure>",
            lambda _event: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.canvas.bind(
            "<Configure>",
            lambda event: self.canvas.itemconfigure("all", width=event.width),
        )


class HomePage(ttk.Frame):
    def __init__(self, parent, *, on_save, on_new_period, on_activate_period, on_update_home_base):
        super().__init__(parent, style="App.TFrame")
        self.on_save = on_save
        self.on_new_period = on_new_period
        self.on_activate_period = on_activate_period
        self.on_update_home_base = on_update_home_base
        self.history_ids: list[int] = []

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)

        summary = ttk.LabelFrame(self, text="Workspace", style="Card.TLabelframe", padding=12)
        summary.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=(0, 8))
        summary.columnconfigure(1, weight=1)

        self.period_var = tk.StringVar()
        self.state_var = tk.StringVar()
        self.home_name_var = tk.StringVar()
        self.home_address_var = tk.StringVar()
        labels = (
            ("Active Period", self.period_var),
            ("State", self.state_var),
            ("Home Base", self.home_name_var),
            ("Home Address", self.home_address_var),
        )
        for index, (label, variable) in enumerate(labels):
            ttk.Label(summary, text=label, style="Surface.TLabel").grid(row=index, column=0, sticky="w", pady=4)
            ttk.Label(summary, textvariable=variable, style="Surface.TLabel").grid(row=index, column=1, sticky="w", pady=4)

        actions = ttk.Frame(summary, style="Surface.TFrame")
        actions.grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Button(actions, text="Save", style="Primary.TButton", command=self.on_save).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="New Pay Period", style="App.TButton", command=self.on_new_period).pack(side="left")

        home_editor = ttk.LabelFrame(self, text="Home Base Settings", style="Card.TLabelframe", padding=12)
        home_editor.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=(0, 8))
        home_editor.columnconfigure(1, weight=1)
        self.home_name_edit = tk.StringVar()
        self.home_address_edit = tk.StringVar()
        ttk.Label(home_editor, text="Name", style="Surface.TLabel").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(home_editor, textvariable=self.home_name_edit).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(home_editor, text="Address", style="Surface.TLabel").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(home_editor, textvariable=self.home_address_edit).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Button(home_editor, text="Update Home Base", style="App.TButton", command=self._save_home_base).grid(
            row=2, column=1, sticky="e", pady=(8, 0)
        )

        history = ttk.LabelFrame(self, text="Recent Pay Periods", style="Card.TLabelframe", padding=12)
        history.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        history.columnconfigure(0, weight=1)
        history.rowconfigure(0, weight=1)
        self.history_list = tk.Listbox(history, bg="#0f141a", fg="#e6edf3", selectbackground="#5ec4a8", activestyle="none", height=10)
        self.history_list.grid(row=0, column=0, sticky="nsew")
        ttk.Button(history, text="Open Selected", style="App.TButton", command=self._activate_selected).grid(
            row=1, column=0, sticky="e", pady=(8, 0)
        )

        mileage = ttk.LabelFrame(self, text="Yearly Mileage", style="Card.TLabelframe", padding=12)
        mileage.grid(row=1, column=1, sticky="nsew", padx=(8, 0))
        mileage.columnconfigure(0, weight=1)
        mileage.columnconfigure(1, weight=1)
        self.total_miles_var = tk.StringVar()
        ttk.Label(mileage, textvariable=self.total_miles_var, style="Accent.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        self.by_type_tree = ttk.Treeview(mileage, columns=("type", "miles"), show="headings", height=6, style="App.Treeview")
        self.by_type_tree.heading("type", text="Type")
        self.by_type_tree.heading("miles", text="Miles")
        self.by_type_tree.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        self.by_client_tree = ttk.Treeview(mileage, columns=("client", "miles"), show="headings", height=6, style="App.Treeview")
        self.by_client_tree.heading("client", text="Client")
        self.by_client_tree.heading("miles", text="Miles")
        self.by_client_tree.grid(row=1, column=1, sticky="nsew")

    def _save_home_base(self) -> None:
        self.on_update_home_base(self.home_name_edit.get(), self.home_address_edit.get())

    def _activate_selected(self) -> None:
        selection = self.history_list.curselection()
        if not selection:
            return
        self.on_activate_period(self.history_ids[selection[0]])

    def apply_snapshot(self, snapshot) -> None:
        self.period_var.set(snapshot.pay_period.start_date.isoformat())
        self.state_var.set("Unsaved changes" if snapshot.dirty else "Saved")
        self.home_name_var.set(snapshot.home_base_name)
        self.home_address_var.set(snapshot.home_base_address or "(not set)")
        self.home_name_edit.set(snapshot.home_base_name)
        self.home_address_edit.set(snapshot.home_base_address)
        self.history_ids = [period.id for period in snapshot.history if period.id is not None]
        self.history_list.delete(0, tk.END)
        for period in snapshot.history:
            active = " (active)" if period.id == snapshot.pay_period.id else ""
            self.history_list.insert(tk.END, f"{period.start_date.isoformat()}{active}")

        self.total_miles_var.set(f"Year {snapshot.yearly_mileage.year}: {snapshot.yearly_mileage.total:.2f} miles")
        for tree in (self.by_type_tree, self.by_client_tree):
            for item in tree.get_children():
                tree.delete(item)
        for segment_type, miles in snapshot.yearly_mileage.by_type.items():
            self.by_type_tree.insert("", tk.END, values=(segment_type, f"{miles:.2f}"))
        for client_name, miles in list(snapshot.yearly_mileage.by_client.items())[:8]:
            self.by_client_tree.insert("", tk.END, values=(client_name, f"{miles:.2f}"))


class TotalsPage(ttk.Frame):
    def __init__(self, parent, *, on_apply):
        super().__init__(parent, style="App.TFrame")
        self.on_apply = on_apply
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)

        editor = ttk.LabelFrame(self, text="Pay Period Settings", style="Card.TLabelframe", padding=12)
        editor.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        editor.columnconfigure(1, weight=1)

        self.start_date_var = tk.StringVar()
        self.hourly_rate_var = tk.StringVar()
        self.yto_rate_var = tk.StringVar()
        self.snow_rate_var = tk.StringVar()
        self.owed_var = tk.StringVar()
        self.tax_rate_var = tk.StringVar()
        fields = (
            ("Start Date", self.start_date_var),
            ("Hourly Rate", self.hourly_rate_var),
            ("YTO Reference", self.yto_rate_var),
            ("Snow Multiplier", self.snow_rate_var),
            ("Owed Back", self.owed_var),
            ("Tax Rate", self.tax_rate_var),
        )
        for row_index, (label, variable) in enumerate(fields):
            ttk.Label(editor, text=label, style="Surface.TLabel").grid(row=row_index, column=0, sticky="w", pady=4)
            ttk.Entry(editor, textvariable=variable).grid(row=row_index, column=1, sticky="ew", pady=4)
        ttk.Button(editor, text="Apply Totals Settings", style="Primary.TButton", command=self._apply).grid(
            row=len(fields), column=1, sticky="e", pady=(10, 0)
        )

        summary = ttk.LabelFrame(self, text="Rollup Summary", style="Card.TLabelframe", padding=12)
        summary.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        summary.columnconfigure(1, weight=1)
        self.summary_vars = {
            "week_one_total": tk.StringVar(),
            "week_two_total": tk.StringVar(),
            "gross_total": tk.StringVar(),
            "estimated_taxes": tk.StringVar(),
            "net_pay": tk.StringVar(),
        }
        summary_labels = (
            ("Week 1 Total", "week_one_total"),
            ("Week 2 Total", "week_two_total"),
            ("Gross Total", "gross_total"),
            ("Estimated Taxes", "estimated_taxes"),
            ("Net Pay", "net_pay"),
        )
        for row_index, (label, key) in enumerate(summary_labels):
            ttk.Label(summary, text=label, style="Surface.TLabel").grid(row=row_index, column=0, sticky="w", pady=4)
            ttk.Label(summary, textvariable=self.summary_vars[key], style="Surface.TLabel").grid(row=row_index, column=1, sticky="w", pady=4)

        day_totals = ttk.LabelFrame(self, text="Day Totals", style="Card.TLabelframe", padding=12)
        day_totals.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(12, 0))
        day_totals.columnconfigure(0, weight=1)
        self.day_totals_tree = ttk.Treeview(day_totals, columns=("day", "total"), show="headings", height=8, style="App.Treeview")
        self.day_totals_tree.heading("day", text="Day")
        self.day_totals_tree.heading("total", text="Total")
        self.day_totals_tree.grid(row=0, column=0, sticky="nsew")

    def _apply(self) -> None:
        self.on_apply(
            self.start_date_var.get(),
            self.hourly_rate_var.get(),
            self.yto_rate_var.get(),
            self.snow_rate_var.get(),
            self.owed_var.get(),
            self.tax_rate_var.get(),
        )

    def apply_snapshot(self, snapshot) -> None:
        self.start_date_var.set(snapshot.pay_period.start_date.isoformat())
        self.hourly_rate_var.set(f"{snapshot.pay_period.hourly_rate:.2f}")
        self.yto_rate_var.set(f"{snapshot.pay_period.yto_rate:.2f}")
        self.snow_rate_var.set(f"{snapshot.pay_period.snow_day_multiplier:.2f}")
        self.owed_var.set(f"{snapshot.pay_period.owed_amount:.2f}")
        self.tax_rate_var.set(f"{snapshot.pay_period.tax_rate:.2f}")
        for key, variable in self.summary_vars.items():
            variable.set(format_currency(getattr(snapshot.summary, key)))
        for item in self.day_totals_tree.get_children():
            self.day_totals_tree.delete(item)
        for weekday in DAY_ORDER:
            self.day_totals_tree.insert("", tk.END, values=(weekday, format_currency(snapshot.summary.day_totals[weekday])))


class DayRowEditor(ttk.Frame):
    def __init__(self, parent, row_snapshot, *, on_edit_client, on_save_row, on_remove_row):
        super().__init__(parent, style="Surface.TFrame", padding=(0, 4))
        self.row_snapshot = row_snapshot
        self.on_edit_client = on_edit_client
        self.on_save_row = on_save_row
        self.on_remove_row = on_remove_row
        self.columnconfigure(4, weight=1)

        self.status_var = tk.StringVar(value=str(row_snapshot.entry.status))
        self.route_stop_var = tk.BooleanVar(value=row_snapshot.entry.route_stop)
        self.rate_override_var = tk.StringVar(
            value="" if row_snapshot.entry.rate_override is None else f"{row_snapshot.entry.rate_override:.2f}"
        )
        self.comments_var = tk.StringVar(value=row_snapshot.entry.comments)

        client_label = row_snapshot.client.name if row_snapshot.client else "Choose Client"
        ttk.Button(
            self,
            text=client_label,
            style="App.TButton",
            command=lambda: self.on_edit_client(self.row_snapshot.entry.id, self.row_snapshot.client.id if self.row_snapshot.client else None),
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Combobox(
            self,
            textvariable=self.status_var,
            values=("", "Done", "YTO", "Skipped", "Off", "Snow_Day"),
            state="readonly",
            width=10,
        ).grid(row=0, column=1, sticky="ew", padx=(0, 6))
        ttk.Checkbutton(self, text="Route", variable=self.route_stop_var).grid(row=0, column=2, sticky="w", padx=(0, 6))
        ttk.Entry(self, textvariable=self.rate_override_var, width=10).grid(row=0, column=3, sticky="ew", padx=(0, 6))
        ttk.Entry(self, textvariable=self.comments_var).grid(row=0, column=4, sticky="ew", padx=(0, 6))
        ttk.Label(self, text=format_currency(self.row_snapshot.effective_rate), style="Surface.TLabel").grid(row=0, column=5, sticky="e", padx=(0, 6))
        amount = self.row_snapshot.amount if isinstance(self.row_snapshot.amount, str) else format_currency(self.row_snapshot.amount)
        ttk.Label(self, text=amount, style="Surface.TLabel").grid(row=0, column=6, sticky="e", padx=(0, 6))
        ttk.Button(self, text="Save", style="App.TButton", command=self._save).grid(row=0, column=7, padx=(0, 6))
        ttk.Button(self, text="X", style="Danger.TButton", command=lambda: self.on_remove_row(self.row_snapshot.entry.id)).grid(row=0, column=8)

    def _save(self) -> None:
        try:
            rate_override = _parse_float(self.rate_override_var.get())
        except ValueError:
            messagebox.showerror("Invalid Rate", "Rate override must be numeric.")
            return
        self.on_save_row(
            self.row_snapshot.entry.id,
            self.row_snapshot.client.id if self.row_snapshot.client else None,
            self.route_stop_var.get(),
            self.status_var.get(),
            rate_override,
            self.comments_var.get(),
        )


class WeekSection(ttk.LabelFrame):
    def __init__(
        self,
        parent,
        *,
        weekday: str,
        week_index: int,
        on_add_row,
        on_edit_client,
        on_save_row,
        on_remove_row,
        on_save_other_task,
        on_generate_route,
        on_add_personal_segment,
        on_edit_segment,
        on_delete_segment,
    ):
        super().__init__(parent, text=f"{weekday} - Week {week_index}", style="Card.TLabelframe", padding=12)
        self.weekday = weekday
        self.week_index = week_index
        self.on_add_row = on_add_row
        self.on_edit_client = on_edit_client
        self.on_save_row = on_save_row
        self.on_remove_row = on_remove_row
        self.on_save_other_task = on_save_other_task
        self.on_generate_route = on_generate_route
        self.on_add_personal_segment = on_add_personal_segment
        self.on_edit_segment = on_edit_segment
        self.on_delete_segment = on_delete_segment
        self.segment_ids: dict[str, int] = {}

        self.columnconfigure(0, weight=1)
        self.meta_var = tk.StringVar()
        ttk.Label(self, textvariable=self.meta_var, style="Surface.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(self, text="Add Row", style="App.TButton", command=lambda: self.on_add_row(self.weekday, self.week_index)).grid(
            row=0, column=1, sticky="e"
        )

        self.rows_host = ttk.Frame(self, style="Surface.TFrame")
        self.rows_host.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 12))
        self.rows_host.columnconfigure(0, weight=1)

        other_task = ttk.Frame(self, style="Surface.TFrame")
        other_task.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        other_task.columnconfigure(1, weight=1)
        self.other_label_var = tk.StringVar()
        self.other_hours_var = tk.StringVar()
        self.other_notes_var = tk.StringVar()
        self.other_amount_var = tk.StringVar()
        ttk.Label(other_task, text="Other Task Label", style="Surface.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(other_task, textvariable=self.other_label_var).grid(row=0, column=1, sticky="ew", padx=(8, 8))
        ttk.Label(other_task, text="Hours", style="Surface.TLabel").grid(row=0, column=2, sticky="w")
        ttk.Entry(other_task, textvariable=self.other_hours_var, width=10).grid(row=0, column=3, sticky="ew", padx=(8, 8))
        ttk.Label(other_task, textvariable=self.other_amount_var, style="Accent.TLabel").grid(row=0, column=4, sticky="e", padx=(0, 8))
        ttk.Button(other_task, text="Save Task", style="App.TButton", command=self._save_other_task).grid(row=0, column=5, sticky="e")

        mileage = ttk.LabelFrame(self, text="Mileage", style="Card.TLabelframe", padding=10)
        mileage.grid(row=3, column=0, columnspan=2, sticky="nsew")
        mileage.columnconfigure(0, weight=1)
        self.route_var = tk.StringVar()
        ttk.Label(mileage, textvariable=self.route_var, style="Surface.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.segment_tree = ttk.Treeview(
            mileage,
            columns=("seq", "type", "from", "to", "miles", "stale"),
            show="headings",
            height=5,
            style="App.Treeview",
        )
        for key, text, width in (
            ("seq", "Seq", 60),
            ("type", "Type", 110),
            ("from", "From", 170),
            ("to", "To", 170),
            ("miles", "Miles", 80),
            ("stale", "Stale", 60),
        ):
            self.segment_tree.heading(key, text=text)
            self.segment_tree.column(key, width=width, anchor="w")
        self.segment_tree.grid(row=1, column=0, sticky="nsew")
        button_row = ttk.Frame(mileage, style="Surface.TFrame")
        button_row.grid(row=2, column=0, sticky="e", pady=(8, 0))
        ttk.Button(button_row, text="Regenerate Route", style="App.TButton", command=lambda: self.on_generate_route(self.weekday, self.week_index)).pack(side="left", padx=(0, 8))
        ttk.Button(button_row, text="Add Personal Segment", style="App.TButton", command=lambda: self.on_add_personal_segment(self.weekday, self.week_index)).pack(side="left", padx=(0, 8))
        ttk.Button(button_row, text="Edit Selected", style="App.TButton", command=self._edit_selected_segment).pack(side="left", padx=(0, 8))
        ttk.Button(button_row, text="Delete Selected", style="Danger.TButton", command=self._delete_selected_segment).pack(side="left")

    def _save_other_task(self) -> None:
        try:
            hours = _parse_float(self.other_hours_var.get()) or 0.0
        except ValueError:
            messagebox.showerror("Invalid Hours", "Other-task hours must be numeric.")
            return
        self.on_save_other_task(self.weekday, self.week_index, self.other_label_var.get(), hours, self.other_notes_var.get())

    def _selected_segment_id(self) -> int | None:
        selection = self.segment_tree.selection()
        if not selection:
            return None
        return self.segment_ids.get(selection[0])

    def _edit_selected_segment(self) -> None:
        segment_id = self._selected_segment_id()
        if segment_id is None:
            return
        self.on_edit_segment(segment_id)

    def _delete_selected_segment(self) -> None:
        segment_id = self._selected_segment_id()
        if segment_id is None:
            return
        self.on_delete_segment(segment_id)

    def apply_snapshot(self, week_snapshot) -> None:
        self.meta_var.set(
            f"{week_snapshot.work_date.isoformat()}  |  Total: {format_currency(week_snapshot.total_pay)}  |  Mileage: {week_snapshot.mileage_total:.2f}"
        )
        for child in self.rows_host.winfo_children():
            child.destroy()
        header = ttk.Frame(self.rows_host, style="Surface.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(4, weight=1)
        for column, text in enumerate(("Client", "Status", "Route", "Override", "Comments", "Rate", "Amount")):
            ttk.Label(header, text=text, style="Surface.TLabel").grid(row=0, column=column, sticky="w", padx=(0, 6))
        for row_index, row_snapshot in enumerate(week_snapshot.rows, start=1):
            widget = DayRowEditor(
                self.rows_host,
                row_snapshot,
                on_edit_client=self.on_edit_client,
                on_save_row=self.on_save_row,
                on_remove_row=self.on_remove_row,
            )
            widget.grid(row=row_index, column=0, sticky="ew")

        self.other_label_var.set(week_snapshot.other_task.label)
        self.other_hours_var.set(f"{week_snapshot.other_task.hours:.2f}")
        self.other_notes_var.set(week_snapshot.other_task.notes)
        if isinstance(week_snapshot.other_task_amount, str):
            self.other_amount_var.set(week_snapshot.other_task_amount)
        else:
            self.other_amount_var.set(format_currency(week_snapshot.other_task_amount))

        self.route_var.set("Route needs review." if week_snapshot.stale_route else "Route is current.")
        self.segment_ids.clear()
        for item in self.segment_tree.get_children():
            self.segment_tree.delete(item)
        for segment in week_snapshot.segments:
            item_id = self.segment_tree.insert(
                "",
                tk.END,
                values=(segment.sequence, segment.segment_type, segment.from_endpoint, segment.to_endpoint, f"{segment.miles:.2f}", "yes" if segment.stale else ""),
            )
            self.segment_ids[item_id] = segment.id


class DayPage(ScrollableFrame):
    def __init__(
        self,
        parent,
        *,
        weekday: str,
        on_add_row,
        on_edit_client,
        on_save_row,
        on_remove_row,
        on_save_other_task,
        on_generate_route,
        on_add_personal_segment,
        on_edit_segment,
        on_delete_segment,
    ):
        super().__init__(parent)
        self.weekday = weekday
        self.sections: dict[int, WeekSection] = {}
        ttk.Label(self.inner, text=weekday, style="App.TLabel", font=("Segoe UI Semibold", 16)).grid(row=0, column=0, sticky="w", pady=(0, 8))
        for row_index, week_index in enumerate(WEEK_INDEXES, start=1):
            section = WeekSection(
                self.inner,
                weekday=weekday,
                week_index=week_index,
                on_add_row=on_add_row,
                on_edit_client=on_edit_client,
                on_save_row=on_save_row,
                on_remove_row=on_remove_row,
                on_save_other_task=on_save_other_task,
                on_generate_route=on_generate_route,
                on_add_personal_segment=on_add_personal_segment,
                on_edit_segment=on_edit_segment,
                on_delete_segment=on_delete_segment,
            )
            section.grid(row=row_index, column=0, sticky="ew", pady=(0, 12))
            self.sections[week_index] = section

    def apply_snapshot(self, day_snapshot) -> None:
        for week_index in WEEK_INDEXES:
            self.sections[week_index].apply_snapshot(day_snapshot.weeks[week_index])
