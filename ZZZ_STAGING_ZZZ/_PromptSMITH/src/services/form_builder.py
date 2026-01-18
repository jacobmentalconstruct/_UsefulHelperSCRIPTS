# src/services/form_builder.py
import tkinter as tk
from tkinter import ttk
from typing import Any, Dict, Tuple


class _WidgetAdapter:
    """
    Wraps different widget types behind a consistent interface:

      - get() -> python value
      - set(value)
      - mark_error(bool) for visual feedback
    """

    def __init__(self, key: str, widget, kind: str, var=None, error_target=None):
        self.key = key
        self.widget = widget
        self.kind = kind
        self.var = var
        # error_target is usually the label or frame we can style
        self.error_target = error_target

    def get(self) -> Any:
        if self.kind in ("entry", "combo"):
            return (self.var.get() if self.var else "").strip()
        if self.kind == "text":
            return self.widget.get("1.0", "end").rstrip("\n")
        if self.kind == "bool":
            return bool(self.var.get())
        return None

    def set(self, value: Any) -> None:
        if self.kind in ("entry", "combo"):
            self.var.set("" if value is None else str(value))
            return
        if self.kind == "text":
            self.widget.delete("1.0", "end")
            self.widget.insert("1.0", "" if value is None else str(value))
            return
        if self.kind == "bool":
            self.var.set(1 if value else 0)

    def mark_error(self, is_error: bool) -> None:
        # Minimal, theme-safe error indication:
        # switch label text to include marker.
        if not self.error_target:
            return
        txt = self.error_target.cget("text")
        if is_error and not txt.endswith(" *"):
            self.error_target.config(text=txt + " *")
        if (not is_error) and txt.endswith(" *"):
            self.error_target.config(text=txt[:-2])


class FormBuilder:
    """
    Builds ttk forms dynamically based on schema dict.

    Expected schema dialect:
    {
      "name": "Role",
      "title": "Role",
      "display_field": "role_name",
      "fields": [
        {"key":"role_name","label":"Role Name","type":"text","required":true},
        {"key":"system_prompt","label":"System Prompt","type":"text_multiline","required":true}
      ],
      "template": "ROLE: {role_name}\n\n{system_prompt}\n"
    }

    Field types supported:
      - "text" -> ttk.Entry
      - "text_multiline" -> tk.Text (with scrollbar)
      - "enum" -> ttk.Combobox (values from "options")
      - "boolean" -> ttk.Checkbutton
      - "integer" -> ttk.Entry + int parse on validate
    """

    def __init__(self, parent: ttk.Frame):
        self.parent = parent
        self.adapters: Dict[str, _WidgetAdapter] = {}
        self._schema = None

        # Fonts for input readability (Text widgets use tk.Text, so we set directly)
        self.entry_font = ("Consolas", 11)  # fallback will occur if not installed
        self.text_font = ("Consolas", 11)

    def clear(self) -> None:
        for child in self.parent.winfo_children():
            child.destroy()
        self.adapters.clear()
        self._schema = None

    def render(self, schema: dict, data: dict) -> None:
        """
        Rebuild the entire form for the given schema.
        """
        self.clear()
        self._schema = schema

        fields = schema.get("fields", [])
        # Form grid: two columns (label, widget) + optional help below
        self.parent.columnconfigure(0, weight=0)
        self.parent.columnconfigure(1, weight=1)

        row = 0
        for field in fields:
            key = field.get("key")
            if not key:
                continue

            label_txt = field.get("label", key)
            required = bool(field.get("required", False))
            if required:
                label_txt += ""  # we add " *" dynamically on error

            label = ttk.Label(self.parent, text=label_txt)
            label.grid(row=row, column=0, sticky="w", padx=(0, 10), pady=(8, 2))

            ftype = field.get("type", "text")
            adapter = self._build_field_widget(row=row, field=field, label_widget=label)
            self.adapters[key] = adapter

            # Optional help text
            help_text = field.get("help")
            if help_text:
                help_lbl = ttk.Label(self.parent, text=help_text, foreground="#666")
                help_lbl.grid(row=row + 1, column=1, sticky="w", pady=(0, 6))
                row += 1

            row += 1

        # Populate defaults/data after widgets exist
        for key, adapter in self.adapters.items():
            adapter.set(data.get(key))

        # add some bottom padding
        spacer = ttk.Frame(self.parent, height=10)
        spacer.grid(row=row + 1, column=0, columnspan=2, sticky="ew")

    def _build_field_widget(self, row: int, field: dict, label_widget: ttk.Label) -> _WidgetAdapter:
        ftype = field.get("type", "text")

        if ftype == "text":
            var = tk.StringVar()
            entry = ttk.Entry(self.parent, textvariable=var)
            # ttk.Entry doesn't support font option consistently across themes; try anyway.
            try:
                entry.configure(font=self.entry_font)
            except tk.TclError:
                pass
            entry.grid(row=row, column=1, sticky="ew", pady=(8, 2))
            return _WidgetAdapter(field["key"], entry, "entry", var=var, error_target=label_widget)

        if ftype == "integer":
            var = tk.StringVar()
            entry = ttk.Entry(self.parent, textvariable=var)
            try:
                entry.configure(font=self.entry_font)
            except tk.TclError:
                pass
            entry.grid(row=row, column=1, sticky="ew", pady=(8, 2))
            return _WidgetAdapter(field["key"], entry, "entry", var=var, error_target=label_widget)

        if ftype == "enum":
            var = tk.StringVar()
            options = field.get("options", [])
            combo = ttk.Combobox(self.parent, textvariable=var, values=options, state="readonly")
            combo.grid(row=row, column=1, sticky="ew", pady=(8, 2))
            return _WidgetAdapter(field["key"], combo, "combo", var=var, error_target=label_widget)

        if ftype == "boolean":
            var = tk.IntVar(value=0)
            chk = ttk.Checkbutton(self.parent, variable=var)
            chk.grid(row=row, column=1, sticky="w", pady=(8, 2))
            return _WidgetAdapter(field["key"], chk, "bool", var=var, error_target=label_widget)

        if ftype == "text_multiline":
            # Wrap tk.Text with its own scrollbar and frame
            frame = ttk.Frame(self.parent)
            frame.grid(row=row, column=1, sticky="nsew", pady=(8, 2))
            frame.columnconfigure(0, weight=1)
            frame.rowconfigure(0, weight=1)

            text = tk.Text(frame, height=8, wrap="word")
            text.configure(font=self.text_font)

            scroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
            text.configure(yscrollcommand=scroll.set)

            text.grid(row=0, column=0, sticky="nsew")
            scroll.grid(row=0, column=1, sticky="ns")
            return _WidgetAdapter(field["key"], text, "text", error_target=label_widget)

        # Fallback to entry
        var = tk.StringVar()
        entry = ttk.Entry(self.parent, textvariable=var)
        entry.grid(row=row, column=1, sticky="ew", pady=(8, 2))
        return _WidgetAdapter(field["key"], entry, "entry", var=var, error_target=label_widget)

    # -------------------------
    # Data + Validation
    # -------------------------

    def get_data(self) -> Dict[str, Any]:
        return {k: adapter.get() for k, adapter in self.adapters.items()}

    def validate(self, schema: dict) -> Tuple[bool, Dict[str, str]]:
        """
        Validates current widget state vs schema.
        Returns: (ok, errors_by_key)
        """
        errors: Dict[str, str] = {}

        fields = schema.get("fields", [])
        field_map = {f.get("key"): f for f in fields if f.get("key")}

        # reset error markers
        for adapter in self.adapters.values():
            adapter.mark_error(False)

        data = self.get_data()

        for key, field in field_map.items():
            required = bool(field.get("required", False))
            ftype = field.get("type", "text")

            value = data.get(key)

            if required:
                if ftype == "boolean":
                    # boolean can be false and still “present”
                    pass
                else:
                    if value is None or str(value).strip() == "":
                        errors[key] = "Required field is empty."

            # Type checks
            if ftype == "integer":
                if str(value).strip() == "":
                    # empty is fine unless required
                    pass
                else:
                    try:
                        int(str(value).strip())
                    except ValueError:
                        errors[key] = "Must be an integer."

            if ftype == "enum":
                options = field.get("options", [])
                if str(value).strip() and options and value not in options:
                    errors[key] = "Value not in allowed options."

        # Mark errors visually
        for key in errors.keys():
            if key in self.adapters:
                self.adapters[key].mark_error(True)

        # If integer fields passed, cast them to int in returned data
        if not errors:
            for key, field in field_map.items():
                if field.get("type") == "integer":
                    raw = data.get(key)
                    if str(raw).strip() != "":
                        data[key] = int(str(raw).strip())
                        # update widget text to normalized int
                        self.adapters[key].set(data[key])

        return (len(errors) == 0), errors
