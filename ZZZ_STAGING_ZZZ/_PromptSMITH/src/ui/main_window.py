# src/ui/main_window.py
import json
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from src.services.form_builder import FormBuilder
from src.services.utils import safe_ui_call


class MainWindow(ttk.Frame):
    """
    Main UI shell:
      - Sidebar: Treeview grouped by schema + "Create New" dropdown
      - Editor: Scrollable dynamic form area
      - Action bar: Save, Copy, Export, Delete
    """

    SIDEBAR_WIDTH = 250

    def __init__(self, root, db, schema_engine, exporter):
        super().__init__(root)

        self.root = root
        self.db = db
        self.schema_engine = schema_engine
        self.exporter = exporter

        self.current_schema_name = None
        self.current_item_id = None

        # FormBuilder is “logic-ish” but interacts with widgets;
        # keep it out of app.py and make it a service.
        self.form_builder = None  # created after editor frame exists

        # ---- Main container layout (pack for main frames) ----
        self._build_layout()

        # ---- Initial schema load + UI population ----
        self.on_schemas_changed()

    def _build_layout(self) -> None:
        # Top-level: left sidebar + right editor
        container = ttk.Frame(self)
        container.pack(side="top", fill="both", expand=True)

        self.sidebar = ttk.Frame(container, width=self.SIDEBAR_WIDTH)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        self.editor = ttk.Frame(container)
        self.editor.pack(side="left", fill="both", expand=True)

        self.action_bar = ttk.Frame(self)
        self.action_bar.pack(side="bottom", fill="x")

        # ---- Sidebar widgets ----
        sidebar_title = ttk.Label(self.sidebar, text="Saved Items")
        sidebar_title.pack(side="top", anchor="w", padx=10, pady=(10, 6))

        self.tree = ttk.Treeview(self.sidebar, show="tree")
        self.tree.pack(side="top", fill="both", expand=True, padx=10, pady=(0, 10))
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        new_frame = ttk.Frame(self.sidebar)
        new_frame.pack(side="bottom", fill="x", padx=10, pady=10)

        ttk.Label(new_frame, text="Create New").pack(side="top", anchor="w")

        self.schema_choice = ttk.Combobox(new_frame, state="readonly", values=[])
        self.schema_choice.pack(side="top", fill="x", pady=(4, 6))

        ttk.Button(new_frame, text="New", command=self._on_create_new).pack(side="top", fill="x")

        # ---- Editor (scrollable form area) ----
        header = ttk.Frame(self.editor)
        header.pack(side="top", fill="x", padx=12, pady=(12, 6))

        self.editor_title = ttk.Label(header, text="Select or create an item", font=("Helvetica", 14))
        self.editor_title.pack(side="left", anchor="w")

        self.schema_status = ttk.Label(header, text="", foreground="#666")
        self.schema_status.pack(side="right", anchor="e")

        from src.ui.scrollable import ScrollableFrame
        self.scrollable = ScrollableFrame(self.editor)
        self.scrollable.pack(side="top", fill="both", expand=True, padx=12, pady=(0, 12))

        # Create the FormBuilder bound to the scrollable content frame
        self.form_builder = FormBuilder(parent=self.scrollable.content)

        # ---- Action bar buttons ----
        ttk.Button(self.action_bar, text="Save to DB", command=self._on_save).pack(
            side="left", padx=8, pady=10
        )
        ttk.Button(self.action_bar, text="Copy to Clipboard", command=self._on_copy).pack(
            side="left", padx=8, pady=10
        )
        ttk.Button(self.action_bar, text="Export to File", command=self._on_export).pack(
            side="left", padx=8, pady=10
        )
        ttk.Button(self.action_bar, text="Delete", command=self._on_delete).pack(
            side="left", padx=8, pady=10
        )

        ttk.Button(self.action_bar, text="Refresh Schemas", command=self.on_schemas_changed).pack(
            side="right", padx=8, pady=10
        )

    # -------------------------
    # Schema + Tree population
    # -------------------------

    @safe_ui_call("Failed to refresh schemas/items")
    def on_schemas_changed(self) -> None:
        """
        Called when:
          - app starts
          - schema engine detects changes
          - user clicks refresh
        """
        schemas = self.schema_engine.get_all_schemas()  # dict[name]->schema dict

        schema_names = sorted(schemas.keys())
        self.schema_choice["values"] = schema_names
        if schema_names and (self.schema_choice.get() not in schema_names):
            self.schema_choice.set(schema_names[0])

        # Rebuild tree grouped by schema
        self.tree.delete(*self.tree.get_children())

        # Parent nodes: schema names
        for schema_name in schema_names:
            parent_id = self.tree.insert("", "end", text=schema_name, open=True, values=())
            # Children: items stored in DB
            items = self.db.list_items(schema_name=schema_name)
            for item in items:
                # Store DB id in the tree item's "iid" (string required)
                self.tree.insert(parent_id, "end", iid=str(item["id"]), text=item["display_name"])

        self.schema_status.config(text=f"Schemas: {len(schema_names)}")

        # If current schema got removed, reset editor
        if self.current_schema_name and self.current_schema_name not in schemas:
            self._reset_editor_state()

    def _reset_editor_state(self) -> None:
        self.current_schema_name = None
        self.current_item_id = None
        self.editor_title.config(text="Select or create an item")
        self.form_builder.clear()

    # -------------------------
    # Tree selection
    # -------------------------

    @safe_ui_call("Failed to load selected item")
    def _on_tree_select(self, _event) -> None:
        sel = self.tree.selection()
        if not sel:
            return

        node_id = sel[0]

        # Parent schema nodes do not have integer DB ids
        if not node_id.isdigit():
            return

        item_id = int(node_id)
        item = self.db.get_item(item_id)
        if not item:
            messagebox.showwarning("Not found", "That item no longer exists in the database.")
            self.on_schemas_changed()
            return

        schema_name = item["schema_name"]
        schema = self.schema_engine.get_schema(schema_name)
        if not schema:
            messagebox.showerror(
                "Schema missing",
                f"Schema '{schema_name}' was not found. Add the schema file back or pick another item.",
            )
            return

        self.current_schema_name = schema_name
        self.current_item_id = item_id

        self.editor_title.config(text=f"{schema.get('title', schema_name)}  —  {item['display_name']}")

        data = json.loads(item["json_data"])
        self.form_builder.render(schema=schema, data=data)

    # -------------------------
    # Create New
    # -------------------------

    @safe_ui_call("Failed to create a new item")
    def _on_create_new(self) -> None:
        schema_name = self.schema_choice.get().strip()
        if not schema_name:
            messagebox.showinfo("No schema", "No schema selected.")
            return

        schema = self.schema_engine.get_schema(schema_name)
        if not schema:
            messagebox.showerror("Schema error", f"Schema '{schema_name}' could not be loaded.")
            return

        self.current_schema_name = schema_name
        self.current_item_id = None

        self.editor_title.config(text=f"New {schema.get('title', schema_name)}")
        self.form_builder.render(schema=schema, data={})

    # -------------------------
    # Actions
    # -------------------------

    @safe_ui_call("Failed to save item")
    def _on_save(self) -> None:
        if not self.current_schema_name:
            messagebox.showinfo("Nothing to save", "Select a schema and create/load an item first.")
            return

        schema = self.schema_engine.get_schema(self.current_schema_name)
        if not schema:
            raise RuntimeError("Current schema missing unexpectedly.")

        ok, errors = self.form_builder.validate(schema=schema)
        if not ok:
            # Render errors in a single message; FormBuilder also marks invalid fields.
            msg = "\n".join(f"- {k}: {v}" for k, v in errors.items())
            messagebox.showwarning("Validation failed", msg)
            return

        data = self.form_builder.get_data()

        # Determine display name (schema can specify display_field)
        display_field = schema.get("display_field")
        display_name = None
        if display_field:
            display_name = str(data.get(display_field, "")).strip() or None
        if not display_name:
            # common fallback keys
            for key in ("name", "title", "role_name", "prompt_name"):
                if key in data and str(data[key]).strip():
                    display_name = str(data[key]).strip()
                    break
        if not display_name:
            display_name = "(untitled)"

        item_id = self.db.upsert_item(
            item_id=self.current_item_id,
            schema_name=self.current_schema_name,
            display_name=display_name,
            json_data=json.dumps(data, ensure_ascii=False, indent=2),
        )
        self.current_item_id = item_id

        self.on_schemas_changed()
        # Re-select in tree if possible
        try:
            self.tree.selection_set(str(item_id))
        except tk.TclError:
            pass

        messagebox.showinfo("Saved", f"Saved '{display_name}' to database.")

    @safe_ui_call("Failed to copy to clipboard")
    def _on_copy(self) -> None:
        if not self.current_schema_name:
            messagebox.showinfo("Nothing to copy", "Load or create an item first.")
            return

        schema = self.schema_engine.get_schema(self.current_schema_name)
        if not schema:
            raise RuntimeError("Current schema missing unexpectedly.")

        ok, errors = self.form_builder.validate(schema=schema)
        if not ok:
            msg = "\n".join(f"- {k}: {v}" for k, v in errors.items())
            messagebox.showwarning("Validation failed", msg)
            return

        data = self.form_builder.get_data()
        text = self.exporter.format_for_injection(schema=schema, data=data)

        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()  # ensure clipboard is updated
        messagebox.showinfo("Copied", "Formatted content copied to clipboard.")

    @safe_ui_call("Failed to export to file")
    def _on_export(self) -> None:
        if not self.current_schema_name:
            messagebox.showinfo("Nothing to export", "Load or create an item first.")
            return

        schema = self.schema_engine.get_schema(self.current_schema_name)
        if not schema:
            raise RuntimeError("Current schema missing unexpectedly.")

        ok, errors = self.form_builder.validate(schema=schema)
        if not ok:
            msg = "\n".join(f"- {k}: {v}" for k, v in errors.items())
            messagebox.showwarning("Validation failed", msg)
            return

        data = self.form_builder.get_data()
        text = self.exporter.format_for_injection(schema=schema, data=data)

        path = filedialog.asksaveasfilename(
            title="Export",
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return

        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

        messagebox.showinfo("Exported", f"Saved to:\n{path}")

    @safe_ui_call("Failed to delete item")
    def _on_delete(self) -> None:
        if not self.current_item_id:
            messagebox.showinfo("Nothing to delete", "Select a saved item to delete.")
            return

        if not messagebox.askyesno("Confirm delete", "Delete this item from the database?"):
            return

        self.db.delete_item(self.current_item_id)
        self._reset_editor_state()
        self.on_schemas_changed()
