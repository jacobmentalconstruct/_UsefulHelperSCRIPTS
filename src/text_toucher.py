"""Create individual UTF-8 files from ProjectMapper's context menu."""

from datetime import datetime
from pathlib import Path
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

if __package__:
    from .patcher import PatchError, validate_target
else:
    from patcher import PatchError, validate_target


EXTENSIONS = (".txt", ".py", ".md", ".json", ".csv", ".log", ".bat", ".sh", ".yaml", "(None)")


def file_name(raw_name, extension=".txt", timestamp=False, now=None):
    name = raw_name.strip()
    if not name or name in (".", ".."):
        raise PatchError("Enter a file name.")
    if re.search(r'[<>:"/\\|?*\x00-\x1f]', name) or name.endswith((".", " ")):
        raise PatchError("Use a file name without path separators or invalid filename characters.")
    if re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])", name.split(".")[0]):
        raise PatchError("That name is reserved by Windows. Choose another name.")
    if extension not in EXTENSIONS:
        raise PatchError("Choose an extension preset, or (None) and enter your own extension in the name.")
    suffix = Path(name).suffix
    base = name[:-len(suffix)] if suffix else name
    # Explicit extensions and dotfiles take precedence over the preset.
    suffix = suffix or ("" if extension == "(None)" or name.startswith(".") else extension)
    stamp = "_" + (now or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S") if timestamp else ""
    return base + stamp + suffix


def create_text_file(folder, name, content, extension=".txt", timestamp=False):
    folder = validate_target(folder)
    if not folder.is_dir():
        raise PatchError("The destination folder no longer exists. Choose another folder.")
    path = validate_target(folder / file_name(name, extension, timestamp))
    data = content.encode("utf-8")
    # Exclusive creation protects existing files even if one appears after validation.
    with path.open("xb") as stream:
        stream.write(data)
    return path


class TextToucherWindow:
    def __init__(self, app, folder):
        self.app = app
        self.colors = app.theme
        self.folder = validate_target(folder)
        if not self.folder.is_dir():
            raise PatchError("Choose an existing destination folder.")
        self.top = tk.Toplevel(app.root)
        self.top.title("New Text File — TextTOUCHER")
        self.top.configure(bg=self.colors["app_bg"])
        self.top.geometry("800x650")
        self.top.minsize(650, 480)
        self.top.protocol("WM_DELETE_WINDOW", self.close)
        self.top.columnconfigure(0, weight=1)
        self.top.rowconfigure(3, weight=1)
        self.name = tk.StringVar(self.top)
        self.extension = tk.StringVar(self.top, ".txt")
        self.timestamp = tk.BooleanVar(self.top, False)
        self.destination = tk.StringVar(self.top)
        self.status = tk.StringVar(self.top, "Name the file, add optional content, then Create File.")
        self.setup_styles()

        path_row = self.frame(self.top)
        path_row.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        path_row.columnconfigure(0, weight=1)
        self.path_label = self.label(path_row, text=str(self.folder), wraplength=520)
        self.path_label.grid(row=0, column=0, sticky="w", padx=8, pady=8)
        self.button(path_row, "Choose Folder…", self.choose_folder, "secondary").grid(row=0, column=1, padx=8)
        inputs = self.frame(self.top)
        inputs.grid(row=1, column=0, sticky="ew", padx=12, pady=6)
        inputs.columnconfigure(1, weight=1)
        self.label(inputs, text="Name:").grid(row=0, column=0, padx=(8, 6), pady=8)
        self.name_entry = tk.Entry(inputs, textvariable=self.name, font=("Arial", 10), relief="flat",
                                   bg=self.colors["field_bg"], fg=self.colors["field_text"],
                                   insertbackground=self.colors["text"], selectbackground=self.colors["selection"])
        self.name_entry.grid(row=0, column=1, sticky="ew", padx=6, pady=8)
        self.extension_box = ttk.Combobox(inputs, textvariable=self.extension, values=EXTENSIONS,
                                          state="readonly", width=9, style="TextToucher.TCombobox")
        self.extension_box.grid(row=0, column=2, padx=8)
        # Style this dropdown's popdown only, rather than all comboboxes in the app.
        popdown = self.top.tk.call("ttk::combobox::PopdownWindow", self.extension_box)
        self.top.tk.call(str(popdown) + ".f.l", "configure", "-background", self.colors["field_bg"],
                         "-foreground", self.colors["text"], "-selectbackground", self.colors["selection"],
                         "-selectforeground", self.colors["text"])
        self.label(self.top, text="FILE CONTENT", bg=self.colors["app_bg"]).grid(
            row=2, column=0, sticky="w", padx=12, pady=(6, 4))
        editor = self.frame(self.top)
        editor.grid(row=3, column=0, sticky="nsew", padx=12)
        editor.rowconfigure(0, weight=1)
        editor.columnconfigure(0, weight=1)
        self.content = tk.Text(editor, wrap="none", undo=True, font=("Consolas", 10),
                               bg=self.colors["log_bg"], fg=self.colors["text"],
                               insertbackground=self.colors["text"], selectbackground=self.colors["selection"],
                               selectforeground=self.colors["text"], relief="flat", padx=10, pady=8)
        self.content.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(editor, command=self.content.yview, style="TextToucher.Vertical.TScrollbar")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(editor, orient="horizontal", command=self.content.xview,
                                    style="TextToucher.Horizontal.TScrollbar")
        horizontal.grid(row=1, column=0, sticky="ew")
        self.content.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        footer = self.frame(self.top)
        footer.grid(row=4, column=0, sticky="ew", padx=12, pady=8)
        footer.columnconfigure(0, weight=1)
        tk.Checkbutton(footer, text="Append date/time to filename", variable=self.timestamp,
                       bg=self.colors["panel_bg"], fg=self.colors["text"], selectcolor=self.colors["tree_bg"],
                       activebackground=self.colors["panel_bg"], activeforeground=self.colors["text"],
                       font=("Arial", 10)).grid(row=0, column=0, sticky="w")
        self.create_button = self.button(footer, "Create File", self.create, "success")
        self.create_button.grid(row=0, column=1, padx=6, pady=6)
        self.preview_label = self.label(self.top, textvariable=self.destination, bg=self.colors["app_bg"], wraplength=620)
        self.preview_label.grid(row=5, column=0, sticky="ew", padx=12, pady=(0, 6))
        self.status_label = self.label(self.top, textvariable=self.status, bg=self.colors["status_bg"],
                                       fg=self.colors["status_text"], wraplength=620, padx=10, pady=8)
        self.status_label.grid(row=6, column=0, sticky="ew", padx=12, pady=(0, 12))
        for variable in (self.name, self.extension, self.timestamp):
            variable.trace_add("write", self.update_preview)
        self.update_preview()
        self.name_entry.focus_set()

    def frame(self, parent):
        return tk.Frame(parent, bg=self.colors["panel_bg"])

    def label(self, parent, **kwargs):
        defaults = dict(bg=self.colors["panel_bg"], fg=self.colors["muted_text"],
                        font=("Arial", 10), anchor="w", justify="left")
        defaults.update(kwargs)
        return tk.Label(parent, **defaults)

    def button(self, parent, text, command, color):
        return self.app._make_button(parent, text, command, self.colors[color], self.colors[color + "_hover"], bold=True)

    def setup_styles(self):
        style = ttk.Style(self.top)
        colors = self.colors
        style.configure("TextToucher.TCombobox", fieldbackground=colors["field_bg"],
                        background=colors["panel_alt_bg"], foreground=colors["text"], arrowcolor=colors["text"])
        style.map("TextToucher.TCombobox", fieldbackground=[("readonly", colors["field_bg"])],
                  foreground=[("readonly", colors["text"])], selectbackground=[("readonly", colors["selection"])])
        for orientation in ("Vertical", "Horizontal"):
            name = f"TextToucher.{orientation}.TScrollbar"
            style.configure(name, background=colors["panel_alt_bg"], troughcolor=colors["log_bg"],
                            arrowcolor=colors["muted_text"], bordercolor=colors["panel_bg"],
                            lightcolor=colors["panel_alt_bg"], darkcolor=colors["panel_alt_bg"])
            style.map(name, background=[("active", colors["secondary"])])

    def update_preview(self, *_):
        try:
            name = file_name(self.name.get(), self.extension.get(), self.timestamp.get())
            self.destination.set(f"New file: {name}")
            self.create_button.configure(state="normal")
        except PatchError as exc:
            self.destination.set(str(exc))
            self.create_button.configure(state="disabled")

    def choose_folder(self):
        selected = filedialog.askdirectory(parent=self.top, initialdir=self.folder)
        if selected:
            try:
                folder = validate_target(selected)
                if not folder.is_dir():
                    raise PatchError("Choose an existing folder.")
            except (OSError, PatchError) as exc:
                self.status.set(str(exc))
                return
            self.folder = folder
            self.path_label.configure(text=str(folder))
            self.update_preview()

    def create(self):
        if self.app.running_tasks or self.app.scan_pending:
            self.status.set("Wait for the current scan or compile to finish before creating a file.")
            return
        try:
            path = create_text_file(self.folder, self.name.get(), self.content.get("1.0", "end-1c"),
                                    self.extension.get(), self.timestamp.get())
        except FileExistsError:
            self.status.set("That file already exists. Choose a different name; nothing was overwritten.")
            return
        except (OSError, ValueError) as exc:
            self.status.set(f"Could not create file: {exc}")
            return
        self.app.file_transformed(path)
        self.name.set("")
        self.content.delete("1.0", "end")
        self.content.edit_reset()
        self.status.set(f"Created: {path}")
        self.name_entry.focus_set()

    def close(self):
        if (self.name.get() or self.content.get("1.0", "end-1c")) and not messagebox.askyesno(
                "Discard new file?", "Close without creating this file?", parent=self.top):
            return
        self.top.destroy()
