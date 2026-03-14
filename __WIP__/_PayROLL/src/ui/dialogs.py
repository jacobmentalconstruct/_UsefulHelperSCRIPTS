from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from domain.payroll import ClientRecord, SEGMENT_TYPES


def _parse_float(value: str) -> float | None:
    stripped = value.strip()
    if not stripped:
        return None
    return float(stripped)


class ClientEditorDialog(tk.Toplevel):
    def __init__(self, parent, *, clients: list[ClientRecord], save_client, initial_client_id: int | None = None):
        super().__init__(parent)
        self.title("Client Editor")
        self.transient(parent)
        self.grab_set()
        self.resizable(True, True)
        self.geometry("860x560")

        self._all_clients = list(clients)
        self._save_client = save_client
        self.result_client_id: int | None = None
        self.current_client_id = initial_client_id
        self.filtered_clients: list[ClientRecord] = []

        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        self.search_var = tk.StringVar()
        self.name_var = tk.StringVar()
        self.default_rate_var = tk.StringVar(value="0.00")
        self.address_var = tk.StringVar()
        self.phone_var = tk.StringVar()
        self.active_var = tk.BooleanVar(value=True)

        header = ttk.Frame(self, style="Panel.TFrame", padding=10)
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Label(header, text="Search", style="Panel.TLabel").pack(side="left")
        search = ttk.Entry(header, textvariable=self.search_var, width=30)
        search.pack(side="left", padx=(8, 12))
        ttk.Button(header, text="New Client", style="App.TButton", command=self._new_client).pack(side="left")

        self.client_list = tk.Listbox(self, bg="#0f141a", fg="#e6edf3", selectbackground="#5ec4a8", activestyle="none")
        self.client_list.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=12)
        self.client_list.bind("<<ListboxSelect>>", self._on_select)

        form = ttk.Frame(self, style="Surface.TFrame", padding=12)
        form.grid(row=1, column=1, sticky="nsew", padx=(6, 12), pady=12)
        form.columnconfigure(1, weight=1)
        form.rowconfigure(5, weight=1)

        labels = [
            ("Name", self.name_var),
            ("Default Rate", self.default_rate_var),
            ("Address", self.address_var),
            ("Phone", self.phone_var),
        ]
        for row_index, (label, variable) in enumerate(labels):
            ttk.Label(form, text=label, style="Surface.TLabel").grid(row=row_index, column=0, sticky="w", pady=4)
            ttk.Entry(form, textvariable=variable).grid(row=row_index, column=1, sticky="ew", pady=4)

        ttk.Label(form, text="Notes", style="Surface.TLabel").grid(row=4, column=0, sticky="nw", pady=4)
        self.notes_text = tk.Text(form, height=10, bg="#0f141a", fg="#e6edf3", insertbackground="#e6edf3", wrap="word")
        self.notes_text.grid(row=4, column=1, sticky="nsew", pady=4)

        ttk.Checkbutton(form, text="Active", variable=self.active_var).grid(row=5, column=1, sticky="w", pady=(8, 0))

        actions = ttk.Frame(self, style="App.TFrame", padding=(12, 0, 12, 12))
        actions.grid(row=2, column=0, columnspan=2, sticky="ew")
        ttk.Button(actions, text="Cancel", style="App.TButton", command=self.destroy).pack(side="right")
        ttk.Button(actions, text="Save & Select", style="Primary.TButton", command=self._save_and_close).pack(side="right", padx=(0, 8))

        self.search_var.trace_add("write", self._refresh_list)
        self._refresh_list()
        if initial_client_id is not None:
            self._load_client(initial_client_id)
        elif self.filtered_clients:
            self._load_client(self.filtered_clients[0].id)

        self.wait_visibility()
        self.focus_set()

    def _refresh_list(self, *_args) -> None:
        filter_text = self.search_var.get().strip().lower()
        self.filtered_clients = [
            client
            for client in sorted(self._all_clients, key=lambda item: item.name.lower())
            if not filter_text or filter_text in client.name.lower() or filter_text in client.address.lower()
        ]
        self.client_list.delete(0, tk.END)
        for client in self.filtered_clients:
            state = "" if client.active else " (inactive)"
            self.client_list.insert(tk.END, f"{client.name}{state}")

    def _load_client(self, client_id: int | None) -> None:
        if client_id is None:
            return
        client = next((item for item in self._all_clients if item.id == client_id), None)
        if client is None:
            return
        self.current_client_id = client.id
        self.name_var.set(client.name)
        self.default_rate_var.set(f"{client.default_rate:.2f}")
        self.address_var.set(client.address)
        self.phone_var.set(client.phone_number)
        self.notes_text.delete("1.0", tk.END)
        self.notes_text.insert("1.0", client.notes)
        self.active_var.set(client.active)
        if client in self.filtered_clients:
            index = self.filtered_clients.index(client)
            self.client_list.selection_clear(0, tk.END)
            self.client_list.selection_set(index)

    def _new_client(self) -> None:
        self.current_client_id = None
        self.name_var.set("")
        self.default_rate_var.set("0.00")
        self.address_var.set("")
        self.phone_var.set("")
        self.notes_text.delete("1.0", tk.END)
        self.active_var.set(True)
        self.client_list.selection_clear(0, tk.END)

    def _on_select(self, _event=None) -> None:
        selection = self.client_list.curselection()
        if not selection:
            return
        client = self.filtered_clients[selection[0]]
        self._load_client(client.id)

    def _save_and_close(self) -> None:
        try:
            default_rate = _parse_float(self.default_rate_var.get()) or 0.0
        except ValueError:
            messagebox.showerror("Invalid Rate", "Default rate must be numeric.", parent=self)
            return
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("Missing Name", "Client name is required.", parent=self)
            return
        client = self._save_client(
            client_id=self.current_client_id,
            name=name,
            default_rate=default_rate,
            address=self.address_var.get(),
            phone_number=self.phone_var.get(),
            notes=self.notes_text.get("1.0", tk.END).strip(),
            active=self.active_var.get(),
        )
        self.result_client_id = client.id
        self.destroy()

    def show(self) -> int | None:
        self.wait_window()
        return self.result_client_id


class MileageSegmentDialog(tk.Toplevel):
    def __init__(self, parent, *, title: str, initial: dict[str, object] | None = None):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)

        initial = initial or {}
        self.result: dict[str, object] | None = None

        frame = ttk.Frame(self, style="Surface.TFrame", padding=12)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(1, weight=1)

        self.sequence_var = tk.StringVar(value=str(initial.get("sequence", 10)))
        self.segment_type_var = tk.StringVar(value=str(initial.get("segment_type", "personal")))
        self.from_var = tk.StringVar(value=str(initial.get("from_endpoint", "")))
        self.to_var = tk.StringVar(value=str(initial.get("to_endpoint", "")))
        self.odo_start_var = tk.StringVar(value="" if initial.get("odometer_start") is None else str(initial.get("odometer_start")))
        self.odo_end_var = tk.StringVar(value="" if initial.get("odometer_end") is None else str(initial.get("odometer_end")))
        self.direct_miles_var = tk.StringVar(value="" if initial.get("direct_miles") is None else str(initial.get("direct_miles")))
        self.notes_var = tk.StringVar(value=str(initial.get("notes", "")))

        fields = (
            ("Sequence", ttk.Entry(frame, textvariable=self.sequence_var)),
            ("Type", ttk.Combobox(frame, textvariable=self.segment_type_var, values=SEGMENT_TYPES, state="readonly")),
            ("From", ttk.Entry(frame, textvariable=self.from_var)),
            ("To", ttk.Entry(frame, textvariable=self.to_var)),
            ("Odometer Start", ttk.Entry(frame, textvariable=self.odo_start_var)),
            ("Odometer End", ttk.Entry(frame, textvariable=self.odo_end_var)),
            ("Direct Miles", ttk.Entry(frame, textvariable=self.direct_miles_var)),
            ("Notes", ttk.Entry(frame, textvariable=self.notes_var)),
        )
        for row_index, (label, widget) in enumerate(fields):
            ttk.Label(frame, text=label, style="Surface.TLabel").grid(row=row_index, column=0, sticky="w", pady=4)
            widget.grid(row=row_index, column=1, sticky="ew", pady=4)

        actions = ttk.Frame(frame, style="Surface.TFrame")
        actions.grid(row=len(fields), column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(actions, text="Cancel", style="App.TButton", command=self.destroy).pack(side="right")
        ttk.Button(actions, text="Save", style="Primary.TButton", command=self._save).pack(side="right", padx=(0, 8))

    def _save(self) -> None:
        try:
            sequence = int(self.sequence_var.get().strip())
            odometer_start = _parse_float(self.odo_start_var.get())
            odometer_end = _parse_float(self.odo_end_var.get())
            direct_miles = _parse_float(self.direct_miles_var.get())
        except ValueError:
            messagebox.showerror("Invalid Number", "Sequence and mileage values must be numeric.", parent=self)
            return
        self.result = {
            "sequence": sequence,
            "segment_type": self.segment_type_var.get().strip() or "personal",
            "from_endpoint": self.from_var.get().strip(),
            "to_endpoint": self.to_var.get().strip(),
            "odometer_start": odometer_start,
            "odometer_end": odometer_end,
            "direct_miles": direct_miles,
            "notes": self.notes_var.get().strip(),
        }
        self.destroy()

    def show(self) -> dict[str, object] | None:
        self.wait_window()
        return self.result
