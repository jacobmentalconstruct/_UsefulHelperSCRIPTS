# PromptArchitect

A Tkinter + ttk desktop app to manage AI Roles and Prompts using JSON schemas.

## Run
```bash
python -m src.app

Add Schemas

Drop new .json schema files into ./schemas/ while the app is running.
The UI will update automatically.
Storage

All items are stored in SQLite: promptarchitect.db


---

# What you can extend next (cleanly, without breaking structure)

### Schema dialect upgrades (FormBuilder + SchemaEngine)
- Add field-level constraints: `min_length`, `max_length`, `regex`, etc.
- Add nested objects / repeatable lists (more complex UI; still doable).
- Add per-field “default” and auto-populate in `render()`.

### DB upgrades (DatabaseManager)
- Add versioning/history table (audit trail).
- Store schema file hash/version per item (helps if schema changes later).

### Tree UX improvements (MainWindow)
- Show item updated timestamps.
- Add search box to filter items.
- Right-click context menu (copy/export/delete).

---

If you want, I can also add (still keeping `app.py` dumb):
- a **schema validation error panel** inside the editor (instead of only messageboxes),
- a **live JSON preview** (readonly) of current form data,
- and a **“duplicate item”** button (very useful for prompt variants).

