import argparse
import csv
import sqlite3
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


TOOL_METADATA = {
    "name": "Daily Mileage Editor",
    "description": "Dark-theme Tkinter editor for daily mileage rollups stored in SQLite.",
    "usage": "python -m src.daily_mileage_editor <workspace_folder_or_db_file>",
}

DAY_ORDER = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]


# ----------------------------
# Database helpers
# ----------------------------

def resolve_db_path(target: Path) -> Path:
    if target.is_dir():
        db_path = target / "mileage.db"
        return db_path
    if target.is_file():
        if target.suffix.lower() == ".db":
            return target
        raise ValueError(f"Expected a workspace folder or .db file, got: {target}")
    raise FileNotFoundError(f"Path not found: {target}")


def connect_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    )
    return cur.fetchone() is not None


def ensure_daily_mileage_table(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_mileage (
            date TEXT PRIMARY KEY,
            day_of_week TEXT NOT NULL,
            daily_miles REAL DEFAULT 0,
            personal_miles REAL,
            commuter_miles REAL,
            work_miles REAL,
            notes TEXT DEFAULT '',
            is_locked INTEGER DEFAULT 0,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()


def parse_date_from_trip_row(row: sqlite3.Row) -> str:
    date_value = (row["date"] or "").strip() if "date" in row.keys() else ""
    if date_value:
        return date_value

    start_time = (row["start_time"] or "").strip() if "start_time" in row.keys() else ""
    if start_time:
        return start_time.split("T")[0]

    return ""


def weekday_name(date_str: str) -> str:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%A")
    except ValueError:
        try:
            return datetime.strptime(date_str, "%m/%d/%Y").strftime("%A")
        except ValueError:
            return ""


def sync_daily_mileage_from_trips(conn: sqlite3.Connection) -> int:
    """
    Rebuilds/refreshes the daily_miles and day_of_week fields from the trips table.
    Manual fields are preserved:
      - personal_miles
      - commuter_miles
      - work_miles
      - notes
      - is_locked
    """
    if not table_exists(conn, "trips"):
        return 0

    cur = conn.cursor()
    cur.execute(
        """
        SELECT date, start_time, distance_miles
        FROM trips
        ORDER BY COALESCE(date, start_time)
        """
    )
    trip_rows = cur.fetchall()

    daily_totals = {}
    for row in trip_rows:
        trip_date = parse_date_from_trip_row(row)
        if not trip_date:
            continue
        miles = float(row["distance_miles"] or 0)
        daily_totals[trip_date] = daily_totals.get(trip_date, 0.0) + miles

    for trip_date, miles in daily_totals.items():
        day_name = weekday_name(trip_date)
        cur.execute(
            """
            INSERT INTO daily_mileage (
                date, day_of_week, daily_miles
            )
            VALUES (?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                day_of_week = excluded.day_of_week,
                daily_miles = excluded.daily_miles,
                updated_at = CURRENT_TIMESTAMP
            """,
            (trip_date, day_name, round(miles, 3)),
        )

    conn.commit()
    return len(daily_totals)


def fetch_daily_rows(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            date,
            day_of_week,
            daily_miles,
            personal_miles,
            commuter_miles,
            work_miles,
            notes,
            is_locked,
            updated_at
        FROM daily_mileage
        ORDER BY date ASC
        """
    )
    return cur.fetchall()


def update_daily_row(
    conn: sqlite3.Connection,
    date_str: str,
    personal_miles,
    commuter_miles,
    work_miles,
    notes: str,
    is_locked: int,
) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE daily_mileage
        SET
            personal_miles = ?,
            commuter_miles = ?,
            work_miles = ?,
            notes = ?,
            is_locked = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE date = ?
        """,
        (personal_miles, commuter_miles, work_miles, notes, is_locked, date_str),
    )
    conn.commit()


# ----------------------------
# UI helpers
# ----------------------------

def as_float_or_none(text: str):
    text = (text or "").strip()
    if text == "":
        return None
    return float(text)


def safe_num(value) -> float:
    return float(value or 0)


def fmt_num(value, decimals=1, blank_if_none=False) -> str:
    if value is None and blank_if_none:
        return ""
    return f"{safe_num(value):.{decimals}f}"


def compute_unallocated(row_dict) -> float:
    daily = safe_num(row_dict.get("daily_miles"))
    personal = safe_num(row_dict.get("personal_miles"))
    commuter = safe_num(row_dict.get("commuter_miles"))
    work = safe_num(row_dict.get("work_miles"))
    return round(daily - (personal + commuter + work), 3)


# ----------------------------
# Main app
# ----------------------------

class DailyMileageEditor(tk.Tk):
    def __init__(self, db_path: Path):
        super().__init__()
        self.db_path = db_path
        self.conn = connect_db(db_path)

        ensure_daily_mileage_table(self.conn)
        sync_daily_mileage_from_trips(self.conn)

        self.title(f"Daily Mileage Editor — {db_path}")
        self.geometry("1500x900")
        self.minsize(1220, 720)

        self.rows_by_date = {}
        self.visible_dates = []
        self.current_date = None
        self._suspend_filter_reload = False

        self._build_style()
        self._build_vars()
        self._build_ui()
        self.reload_grid()

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------------------
    # Theme / style
    # ------------------------

    def _build_style(self):
        bg = "#141414"
        card = "#1d1d1d"
        field = "#222222"
        text = "#e8e8e8"
        muted = "#b2b2b2"
        accent = "#6ea8fe"
        border = "#383838"

        self.colors = {
            "bg": bg,
            "card": card,
            "field": field,
            "text": text,
            "muted": muted,
            "accent": accent,
            "border": border,
            "good": "#1f3a2a",
            "warn": "#4a3912",
            "bad": "#4a1f1f",
            "locked": "#243447",
        }

        self.configure(bg=bg)

        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure(".", background=bg, foreground=text, fieldbackground=field)
        style.configure("TFrame", background=bg)
        style.configure("Card.TFrame", background=card)
        style.configure("TLabel", background=bg, foreground=text)
        style.configure("Muted.TLabel", background=bg, foreground=muted)
        style.configure("Card.TLabel", background=card, foreground=text)
        style.configure("Header.TLabel", background=bg, foreground=text, font=("Segoe UI", 15, "bold"))
        style.configure("TButton", background=field, foreground=text, borderwidth=1, focusthickness=0, padding=8)
        style.map("TButton", background=[("active", "#2d2d2d")])

        style.configure(
            "Treeview",
            background=card,
            fieldbackground=card,
            foreground=text,
            rowheight=28,
            bordercolor=border,
            borderwidth=1,
        )
        style.configure(
            "Treeview.Heading",
            background="#2a2a2a",
            foreground=text,
            bordercolor=border,
            relief="flat",
            font=("Segoe UI", 10, "bold"),
        )
        style.map(
            "Treeview",
            background=[("selected", "#2f4f6f")],
            foreground=[("selected", "#ffffff")],
        )

        style.configure("TEntry", fieldbackground=field, foreground=text, insertcolor=text)
        style.configure("TCheckbutton", background=bg, foreground=text)
        style.map("TCheckbutton", background=[("active", bg)])

    # ------------------------
    # State vars
    # ------------------------

    def _build_vars(self):
        self.date_var = tk.StringVar()
        self.day_var = tk.StringVar()
        self.daily_var = tk.StringVar()

        self.personal_var = tk.StringVar()
        self.commuter_var = tk.StringVar()
        self.work_var = tk.StringVar()

        self.unallocated_var = tk.StringVar(value="0.0")
        self.locked_var = tk.IntVar(value=0)

        self.summary_start_var = tk.StringVar(value="—")
        self.summary_end_var = tk.StringVar(value="—")
        self.summary_total_var = tk.StringVar(value="0.0")
        self.summary_personal_var = tk.StringVar(value="0.0")
        self.summary_commuter_var = tk.StringVar(value="0.0")
        self.summary_work_var = tk.StringVar(value="0.0")
        self.summary_unallocated_var = tk.StringVar(value="0.0")
        self.summary_incomplete_var = tk.StringVar(value="0")

        self.day_filter_vars = {}
        for day_name in DAY_ORDER:
            var = tk.BooleanVar(value=True)
            var.trace_add("write", self._on_day_filter_changed)
            self.day_filter_vars[day_name] = var

        for var in (self.personal_var, self.commuter_var, self.work_var):
            var.trace_add("write", lambda *args: self.update_editor_unallocated())

    # ------------------------
    # Layout
    # ------------------------

    def _build_ui(self):
        root = ttk.Frame(self)
        root.pack(fill="both", expand=True, padx=12, pady=12)

        self._build_toolbar(root)

        body = ttk.Panedwindow(root, orient="horizontal")
        body.pack(fill="both", expand=True, pady=(10, 0))

        left = ttk.Frame(body)
        right = ttk.Frame(body)
        body.add(left, weight=4)
        body.add(right, weight=2)

        self._build_table_panel(left)
        self._build_editor_panel(right)

    def _build_toolbar(self, parent):
        bar = ttk.Frame(parent)
        bar.pack(fill="x")

        left = ttk.Frame(bar)
        left.pack(side="left", fill="x", expand=True)

        right = ttk.Frame(bar)
        right.pack(side="right")

        ttk.Label(left, text="Daily Mileage Editor", style="Header.TLabel").pack(anchor="w")
        ttk.Label(left, text=str(self.db_path), style="Muted.TLabel").pack(anchor="w", pady=(2, 0))

        ttk.Button(right, text="Refresh From Trips", command=self.refresh_from_trips).pack(side="left", padx=(0, 8))
        ttk.Button(right, text="Save Selected", command=self.save_selected_row).pack(side="left", padx=(0, 8))
        ttk.Button(right, text="Export CSV", command=self.export_csv).pack(side="left")

        filter_row = ttk.Frame(parent)
        filter_row.pack(fill="x", pady=(10, 0))

        ttk.Label(filter_row, text="Show Days:", style="Muted.TLabel").pack(side="left", padx=(0, 8))

        ttk.Button(filter_row, text="All", command=self.show_all_days).pack(side="left", padx=(0, 6))
        ttk.Button(filter_row, text="Weekdays", command=self.show_weekdays_only).pack(side="left", padx=(0, 6))
        ttk.Button(filter_row, text="Weekends", command=self.show_weekends_only).pack(side="left", padx=(0, 12))

        for day_name in DAY_ORDER:
            ttk.Checkbutton(
                filter_row,
                text=day_name[:3],
                variable=self.day_filter_vars[day_name]
            ).pack(side="left", padx=(0, 4))

    def _build_table_panel(self, parent):
        panel = ttk.Frame(parent)
        panel.pack(fill="both", expand=True)

        columns = (
            "date",
            "day_of_week",
            "daily_miles",
            "personal_miles",
            "commuter_miles",
            "work_miles",
            "unallocated",
            "running_total",
            "notes",
        )

        self.tree = ttk.Treeview(parent, columns=columns, show="headings", selectmode="browse")

        headings = {
            "date": "Date",
            "day_of_week": "Day of Week",
            "daily_miles": "Daily Miles",
            "personal_miles": "Personal Miles",
            "commuter_miles": "Commuter Miles",
            "work_miles": "Work Miles",
            "unallocated": "Unallocated",
            "running_total": "Running Total",
            "notes": "Notes",
        }

        widths = {
            "date": 95,
            "day_of_week": 120,
            "daily_miles": 95,
            "personal_miles": 105,
            "commuter_miles": 110,
            "work_miles": 95,
            "unallocated": 100,
            "running_total": 105,
            "notes": 260,
        }

        for col in columns:
            self.tree.heading(col, text=headings[col])
            anchor = "w" if col in {"date", "day_of_week", "notes"} else "e"
            self.tree.column(col, width=widths[col], anchor=anchor, stretch=(col == "notes"))

        vsb = ttk.Scrollbar(parent, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(parent, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.pack(side="top", fill="both", expand=True)
        hsb.pack(side="bottom", fill="x")
        vsb.pack(side="right", fill="y")

        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        self.tree.tag_configure("balanced", background=self.colors["good"], foreground="#eef7ef")
        self.tree.tag_configure("incomplete", background=self.colors["warn"], foreground="#fff3d6")
        self.tree.tag_configure("over", background=self.colors["bad"], foreground="#ffdede")
        self.tree.tag_configure("locked", background=self.colors["locked"], foreground="#e6f1ff")

    def _build_editor_panel(self, parent):
        editor_card = ttk.Frame(parent, style="Card.TFrame")
        editor_card.pack(fill="x", pady=(0, 12))

        top = ttk.Frame(editor_card, style="Card.TFrame")
        top.pack(fill="x", padx=14, pady=(14, 10))

        ttk.Label(top, text="Selected Day", style="Card.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 10), columnspan=2)

        self._form_row(top, 1, "Date", self.date_var, readonly=True)
        self._form_row(top, 2, "Day", self.day_var, readonly=True)
        self._form_row(top, 3, "Daily Miles", self.daily_var, readonly=True)
        self._form_row(top, 4, "Personal Miles", self.personal_var)
        self._form_row(top, 5, "Commuter Miles", self.commuter_var)
        self._form_row(top, 6, "Work Miles", self.work_var)
        self._form_row(top, 7, "Unallocated", self.unallocated_var, readonly=True)

        ttk.Checkbutton(
            top,
            text="Lock this day",
            variable=self.locked_var
        ).grid(row=8, column=0, columnspan=2, sticky="w", pady=(10, 8))

        ttk.Label(top, text="Notes", style="Card.TLabel").grid(row=9, column=0, sticky="nw", pady=(4, 6))
        self.notes_text = tk.Text(
            top,
            height=5,
            bg=self.colors["field"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=self.colors["border"],
            wrap="word",
            font=("Segoe UI", 10),
        )
        self.notes_text.grid(row=9, column=1, sticky="ew", pady=(4, 6))

        button_row = ttk.Frame(editor_card, style="Card.TFrame")
        button_row.pack(fill="x", padx=14, pady=(0, 14))
        ttk.Button(button_row, text="Save Selected", command=self.save_selected_row).pack(side="left")

        summary_card = ttk.Frame(parent, style="Card.TFrame")
        summary_card.pack(fill="both", expand=False)

        summary_inner = ttk.Frame(summary_card, style="Card.TFrame")
        summary_inner.pack(fill="both", expand=True, padx=14, pady=14)

        ttk.Label(summary_inner, text="Summary", style="Card.TLabel").grid(row=0, column=0, sticky="w", columnspan=2, pady=(0, 2))
        ttk.Label(summary_inner, text="Summary reflects visible rows", style="Card.TLabel").grid(
            row=1, column=0, sticky="w", columnspan=2, pady=(0, 10)
        )

        self._summary_row(summary_inner, 2, "Start Date", self.summary_start_var)
        self._summary_row(summary_inner, 3, "End Date", self.summary_end_var)
        self._summary_row(summary_inner, 4, "Total Miles", self.summary_total_var)
        self._summary_row(summary_inner, 5, "Personal Miles", self.summary_personal_var)
        self._summary_row(summary_inner, 6, "Commuter Miles", self.summary_commuter_var)
        self._summary_row(summary_inner, 7, "Work Miles", self.summary_work_var)
        self._summary_row(summary_inner, 8, "Unallocated Total", self.summary_unallocated_var)
        self._summary_row(summary_inner, 9, "Incomplete Days", self.summary_incomplete_var)

    def _form_row(self, parent, row, label, var, readonly=False):
        ttk.Label(parent, text=label, style="Card.TLabel").grid(row=row, column=0, sticky="w", pady=4, padx=(0, 10))
        entry = ttk.Entry(parent, textvariable=var)
        entry.grid(row=row, column=1, sticky="ew", pady=4)
        if readonly:
            entry.state(["readonly"])
        parent.columnconfigure(1, weight=1)

    def _summary_row(self, parent, row, label, var):
        ttk.Label(parent, text=label, style="Card.TLabel").grid(row=row, column=0, sticky="w", pady=4, padx=(0, 12))
        ttk.Label(parent, textvariable=var, style="Card.TLabel").grid(row=row, column=1, sticky="e", pady=4)
        parent.columnconfigure(1, weight=1)

    # ------------------------
    # Filter helpers
    # ------------------------

    def _on_day_filter_changed(self, *args):
        if self._suspend_filter_reload:
            return
        if hasattr(self, "tree"):
            self.reload_grid()

    def day_is_visible(self, day_name: str) -> bool:
        if day_name in self.day_filter_vars:
            return bool(self.day_filter_vars[day_name].get())
        return True

    def set_day_filter_preset(self, allowed_days):
        self._suspend_filter_reload = True
        try:
            for day_name in DAY_ORDER:
                self.day_filter_vars[day_name].set(day_name in allowed_days)
        finally:
            self._suspend_filter_reload = False
        self.reload_grid()

    def show_all_days(self):
        self.set_day_filter_preset(set(DAY_ORDER))

    def show_weekdays_only(self):
        self.set_day_filter_preset({"Monday", "Tuesday", "Wednesday", "Thursday", "Friday"})

    def show_weekends_only(self):
        self.set_day_filter_preset({"Saturday", "Sunday"})

    # ------------------------
    # Grid / editor sync
    # ------------------------

    def reload_grid(self):
        rows = fetch_daily_rows(self.conn)
        all_rows = [dict(row) for row in rows]
        self.rows_by_date = {row["date"]: row for row in all_rows}

        visible_rows = [row for row in all_rows if self.day_is_visible(row.get("day_of_week", ""))]
        self.visible_dates = [row["date"] for row in visible_rows]

        self.tree.delete(*self.tree.get_children())

        running_total = 0.0
        for row_dict in visible_rows:
            date_str = row_dict["date"]
            running_total += safe_num(row_dict["daily_miles"])
            unallocated = compute_unallocated(row_dict)

            tags = []
            if safe_num(row_dict.get("is_locked")) == 1:
                tags.append("locked")
            elif abs(unallocated) <= 0.05:
                tags.append("balanced")
            elif unallocated > 0.05:
                tags.append("incomplete")
            else:
                tags.append("over")

            self.tree.insert(
                "",
                "end",
                iid=date_str,
                values=(
                    date_str,
                    row_dict["day_of_week"],
                    fmt_num(row_dict["daily_miles"]),
                    fmt_num(row_dict["personal_miles"], blank_if_none=True),
                    fmt_num(row_dict["commuter_miles"], blank_if_none=True),
                    fmt_num(row_dict["work_miles"], blank_if_none=True),
                    fmt_num(unallocated),
                    fmt_num(running_total),
                    row_dict.get("notes", ""),
                ),
                tags=tags,
            )

        self.update_summary_panel(visible_rows)

        if self.current_date and self.current_date in self.visible_dates:
            self.tree.selection_set(self.current_date)
            self.tree.focus(self.current_date)
            self.populate_editor(self.current_date)
        else:
            all_items = self.tree.get_children()
            if all_items:
                first = all_items[0]
                self.tree.selection_set(first)
                self.tree.focus(first)
                self.populate_editor(first)
            else:
                self.clear_editor()

    def populate_editor(self, date_str: str):
        row = self.rows_by_date.get(date_str)
        if not row:
            self.clear_editor()
            return

        self.current_date = date_str

        self.date_var.set(row["date"])
        self.day_var.set(row["day_of_week"])
        self.daily_var.set(fmt_num(row["daily_miles"]))
        self.personal_var.set(fmt_num(row["personal_miles"], blank_if_none=True))
        self.commuter_var.set(fmt_num(row["commuter_miles"], blank_if_none=True))
        self.work_var.set(fmt_num(row["work_miles"], blank_if_none=True))
        self.locked_var.set(int(row["is_locked"] or 0))

        self.notes_text.delete("1.0", "end")
        self.notes_text.insert("1.0", row.get("notes", "") or "")

        self.update_editor_unallocated()

    def clear_editor(self):
        self.current_date = None
        self.date_var.set("")
        self.day_var.set("")
        self.daily_var.set("")
        self.personal_var.set("")
        self.commuter_var.set("")
        self.work_var.set("")
        self.unallocated_var.set("0.0")
        self.locked_var.set(0)
        self.notes_text.delete("1.0", "end")

    def update_editor_unallocated(self):
        try:
            daily = safe_num(self.daily_var.get())
            personal = safe_num(as_float_or_none(self.personal_var.get()))
            commuter = safe_num(as_float_or_none(self.commuter_var.get()))
            work = safe_num(as_float_or_none(self.work_var.get()))
            unallocated = round(daily - (personal + commuter + work), 3)
            self.unallocated_var.set(fmt_num(unallocated))
        except Exception:
            self.unallocated_var.set("ERR")

    def update_summary_panel(self, visible_rows):
        if not visible_rows:
            self.summary_start_var.set("—")
            self.summary_end_var.set("—")
            self.summary_total_var.set("0.0")
            self.summary_personal_var.set("0.0")
            self.summary_commuter_var.set("0.0")
            self.summary_work_var.set("0.0")
            self.summary_unallocated_var.set("0.0")
            self.summary_incomplete_var.set("0")
            return

        start_date = visible_rows[0]["date"]
        end_date = visible_rows[-1]["date"]

        total = sum(safe_num(r["daily_miles"]) for r in visible_rows)
        personal = sum(safe_num(r["personal_miles"]) for r in visible_rows)
        commuter = sum(safe_num(r["commuter_miles"]) for r in visible_rows)
        work = sum(safe_num(r["work_miles"]) for r in visible_rows)
        unallocated_total = sum(compute_unallocated(r) for r in visible_rows)
        incomplete_count = sum(1 for r in visible_rows if abs(compute_unallocated(r)) > 0.05)

        self.summary_start_var.set(start_date)
        self.summary_end_var.set(end_date)
        self.summary_total_var.set(fmt_num(total))
        self.summary_personal_var.set(fmt_num(personal))
        self.summary_commuter_var.set(fmt_num(commuter))
        self.summary_work_var.set(fmt_num(work))
        self.summary_unallocated_var.set(fmt_num(unallocated_total))
        self.summary_incomplete_var.set(str(incomplete_count))

    # ------------------------
    # Events / actions
    # ------------------------

    def on_tree_select(self, _event=None):
        selected = self.tree.selection()
        if not selected:
            return
        self.populate_editor(selected[0])

    def refresh_from_trips(self):
        synced = sync_daily_mileage_from_trips(self.conn)
        self.reload_grid()
        messagebox.showinfo("Refresh Complete", f"Updated daily rollups for {synced} day(s) from trips.")

    def save_selected_row(self):
        if not self.current_date:
            messagebox.showwarning("No Selection", "Select a day first.")
            return

        try:
            personal = as_float_or_none(self.personal_var.get())
            commuter = as_float_or_none(self.commuter_var.get())
            work = as_float_or_none(self.work_var.get())
        except ValueError:
            messagebox.showerror("Invalid Number", "Personal, commuter, and work miles must be numeric or blank.")
            return

        notes = self.notes_text.get("1.0", "end").strip()
        is_locked = int(self.locked_var.get())

        update_daily_row(
            self.conn,
            date_str=self.current_date,
            personal_miles=personal,
            commuter_miles=commuter,
            work_miles=work,
            notes=notes,
            is_locked=is_locked,
        )
        self.reload_grid()

    def export_csv(self):
        visible_rows = [self.rows_by_date[date_str] for date_str in self.visible_dates if date_str in self.rows_by_date]
        if not visible_rows:
            messagebox.showwarning("Nothing to Export", "There are no visible daily mileage rows to export.")
            return

        suggested = self.db_path.with_name("daily_mileage_export.csv")
        save_path = filedialog.asksaveasfilename(
            title="Export Daily Mileage CSV",
            defaultextension=".csv",
            initialfile=suggested.name,
            filetypes=[("CSV Files", "*.csv")],
        )
        if not save_path:
            return

        running_total = 0.0
        with open(save_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Date",
                "Day of Week",
                "Daily Miles",
                "Personal Miles",
                "Commuter Miles",
                "Work Miles",
                "Unallocated",
                "Running Total",
                "Notes",
            ])

            for row_dict in visible_rows:
                running_total += safe_num(row_dict["daily_miles"])
                unallocated = compute_unallocated(row_dict)

                writer.writerow([
                    row_dict["date"],
                    row_dict["day_of_week"],
                    fmt_num(row_dict["daily_miles"]),
                    fmt_num(row_dict["personal_miles"]),
                    fmt_num(row_dict["commuter_miles"]),
                    fmt_num(row_dict["work_miles"]),
                    fmt_num(unallocated),
                    fmt_num(running_total),
                    row_dict.get("notes", ""),
                ])

        messagebox.showinfo("Export Complete", f"CSV written to:\n{save_path}")

    def on_close(self):
        try:
            self.conn.close()
        finally:
            self.destroy()


# ----------------------------
# CLI
# ----------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Dark-theme Tkinter editor for daily mileage rollups."
    )
    parser.add_argument(
        "target",
        help="Path to a workspace folder containing mileage.db, or a direct mileage.db path",
    )
    args = parser.parse_args()

    target = Path(args.target)
    db_path = resolve_db_path(target)

    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    app = DailyMileageEditor(db_path)
    app.mainloop()


if __name__ == "__main__":
    main()