from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk

# Import the CLI from the sibling module
try:
    # Try relative import (standard when running via 'python -m src.app')
    from .linenumberizer import main as ln_main
except ImportError:
    try:
        # Fallback for direct script execution ('python app.py')
        import linenumberizer
        ln_main = linenumberizer.main
    except ImportError as e:
        raise SystemExit("Could not import linenumberizer.py. Ensure it sits next to this GUI file.\n" + str(e))

APP_TITLE = "LineNumberizer – Helper"

STYLES = ("pipe", "colon", "bracket")
AST_MODES = ("tree", "flat", "semantic")

# ----------------------------
# Path utilities
# ----------------------------

def split_stem_ext(path: str):
    base = os.path.basename(path)
    stem, ext = os.path.splitext(base)
    return stem, ext


def default_output_for(input_path: str, op: str, style: str, ast_mode: str) -> str:
    """Return the suggested output path per user preference (underscore tag)."""
    if not input_path:
        return ""
    folder = os.path.dirname(os.path.abspath(input_path))
    stem, ext = split_stem_ext(input_path)
    if op == "annotate":
        # Example: foo.py -> foo._lineNUMBERED.pipe.py
        out_name = f"{stem}._lineNUMBERED.{style}{ext}"
    elif op == "strip":
        out_name = f"{stem}._stripped{ext}"
    elif op == "map":
        out_name = f"{stem}._linemap.json"
    elif op == "ast":
        out_name = f"{stem}._ast.{ast_mode}.json"
    else:
        out_name = f"{stem}.out"
    return os.path.join(folder, out_name)


# ----------------------------
# Worker
# ----------------------------

def run_cli_async(argv, on_done):
    def _worker():
        try:
            rc = ln_main(argv)
        except Exception as e:
            on_done(False, f"error: {e}")
            return
        ok = (rc == 0)
        on_done(ok, f"Completed with exit code {rc}")
    t = threading.Thread(target=_worker, daemon=True)
    t.start()


# ----------------------------
# GUI
# ----------------------------

class App(ttk.Frame):
    def __init__(self, master: tk.Tk):
        super().__init__(master, padding=12)
        self.master = master
        self.grid(sticky="nsew")

        # Vars
        self.var_file = tk.StringVar()
        self.var_out = tk.StringVar()
        self.var_op = tk.StringVar(value="annotate")
        self.var_style = tk.StringVar(value=STYLES[0])
        self.var_start = tk.IntVar(value=1)
        self.var_width = tk.IntVar(value=0)
        self.var_ast_mode = tk.StringVar(value=AST_MODES[0])

        # Layout config
        master.title(APP_TITLE)
        master.minsize(600, 320)
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)

        self.columnconfigure(1, weight=1)
        self.rowconfigure(12, weight=1)

        # File input
        ttk.Label(self, text="Input file").grid(row=0, column=0, sticky="w")
        row0 = ttk.Frame(self)
        row0.grid(row=0, column=1, sticky="ew", pady=(0, 6))
        row0.columnconfigure(0, weight=1)
        ttk.Entry(row0, textvariable=self.var_file).grid(row=0, column=0, sticky="ew")
        ttk.Button(row0, text="Browse…", command=self.pick_file).grid(row=0, column=1, padx=(6,0))

        # Operation
        ttk.Label(self, text="Operation").grid(row=1, column=0, sticky="w")
        row1 = ttk.Frame(self)
        row1.grid(row=1, column=1, sticky="w", pady=(0, 6))
        for i, (val, text) in enumerate((
            ("annotate", "Annotate"),
            ("strip", "Strip"),
            ("map", "Map"),
            ("ast", "AST (Python)"),
        )):
            rb = ttk.Radiobutton(row1, value=val, text=text, variable=self.var_op, command=self._update_out_suggestion)
            rb.grid(row=0, column=i, padx=(0,12))

        # Annotate options
        self.annot_frame = ttk.LabelFrame(self, text="Annotate options")
        self.annot_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        for c in range(0, 6):
            self.annot_frame.columnconfigure(c, weight=0)
        self.annot_frame.columnconfigure(3, weight=1)

        ttk.Label(self.annot_frame, text="Style").grid(row=0, column=0, sticky="w")
        style_cb = ttk.Combobox(self.annot_frame, values=STYLES, textvariable=self.var_style, width=10, state="readonly")
        style_cb.grid(row=0, column=1, sticky="w", padx=(6, 18))
        style_cb.bind("<<ComboboxSelected>>", lambda e: self._update_out_suggestion())

        ttk.Label(self.annot_frame, text="Start").grid(row=0, column=2, sticky="e")
        ttk.Spinbox(self.annot_frame, from_=1, to=10_000_000, textvariable=self.var_start, width=8).grid(row=0, column=3, sticky="w", padx=(6, 18))

        ttk.Label(self.annot_frame, text="Min Width (0=auto)").grid(row=0, column=4, sticky="e")
        ttk.Spinbox(self.annot_frame, from_=0, to=12, textvariable=self.var_width, width=6).grid(row=0, column=5, sticky="w")

        # AST options
        self.ast_frame = ttk.LabelFrame(self, text="AST options (Python)")
        self.ast_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        self.ast_frame.columnconfigure(1, weight=1)
        ttk.Label(self.ast_frame, text="Mode").grid(row=0, column=0, sticky="w")
        ast_cb = ttk.Combobox(self.ast_frame, values=AST_MODES, textvariable=self.var_ast_mode, width=10, state="readonly")
        ast_cb.grid(row=0, column=1, sticky="w", padx=(6, 18))
        ast_cb.bind("<<ComboboxSelected>>", lambda e: self._update_out_suggestion())

        # Output
        ttk.Label(self, text="Output path").grid(row=4, column=0, sticky="w")
        row3 = ttk.Frame(self)
        row3.grid(row=4, column=1, sticky="ew", pady=(0, 6))
        row3.columnconfigure(0, weight=1)
        ttk.Entry(row3, textvariable=self.var_out).grid(row=0, column=0, sticky="ew")
        ttk.Button(row3, text="Change…", command=self.pick_out).grid(row=0, column=1, padx=(6,0))

        # Action buttons
        bar = ttk.Frame(self)
        bar.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(6, 6))
        bar.columnconfigure(0, weight=1)
        self.btn_run = ttk.Button(bar, text="Run", command=self.on_run)
        self.btn_run.grid(row=0, column=1, sticky="e")

        # Log output
        ttk.Label(self, text="Log").grid(row=6, column=0, sticky="w")
        self.log = tk.Text(self, height=8, wrap="word")
        self.log.grid(row=7, column=0, columnspan=2, sticky="nsew")
        self.log.configure(state="disabled")

        self._update_controls()

    # ------------- UI helpers -------------
    def pick_file(self):
        path = filedialog.askopenfilename(title="Choose a text file")
        if path:
            self.var_file.set(path)
            self._update_out_suggestion()

    def pick_out(self):
        base = self.var_out.get() or default_output_for(self.var_file.get(), self.var_op.get(), self.var_style.get(), self.var_ast_mode.get())
        initialdir = os.path.dirname(base) if base else None
        initialfile = os.path.basename(base) if base else None
        path = filedialog.asksaveasfilename(title="Save output as", initialdir=initialdir, initialfile=initialfile)
        if path:
            self.var_out.set(path)

    def _update_out_suggestion(self):
        self.var_out.set(default_output_for(self.var_file.get(), self.var_op.get(), self.var_style.get(), self.var_ast_mode.get()))
        self._update_controls()

    def _update_controls(self):
        # Enable annotate options only for annotate op
        annot = (self.var_op.get() == "annotate")
        for child in self.annot_frame.winfo_children():
            try:
                child.configure(state=("!disabled" if annot else "disabled"))
            except tk.TclError:
                pass
        # Enable AST options only for ast op
        ast_enabled = (self.var_op.get() == "ast")
        for child in self.ast_frame.winfo_children():
            try:
                child.configure(state=("!disabled" if ast_enabled else "disabled"))
            except tk.TclError:
                pass

    def _append_log(self, msg: str):
        self.log.configure(state="normal")
        self.log.insert("end", msg.rstrip()+"\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def on_run(self):
        infile = self.var_file.get().strip()
        if not infile:
            messagebox.showerror(APP_TITLE, "Please choose an input file.")
            return
        if not os.path.isfile(infile):
            messagebox.showerror(APP_TITLE, "Input path does not exist or is not a file.")
            return

        op = self.var_op.get()
        out = self.var_out.get().strip() or default_output_for(infile, op, self.var_style.get(), self.var_ast_mode.get())
        argv = [op, infile]

        if op == "annotate":
            argv += ["--out", out, "--style", self.var_style.get(), "--start", str(self.var_start.get()), "--width", str(self.var_width.get())]
        elif op == "strip":
            argv += ["--out", out]
        elif op == "map":
            argv += ["--out", out]
        elif op == "ast":
            argv += ["--out", out, "--mode", self.var_ast_mode.get()]
        else:
            messagebox.showerror(APP_TITLE, f"Unknown operation: {op}")
            return

        self.btn_run.configure(state="disabled")
        self._append_log(f"Running: linenumberizer {' '.join(argv)}")

        def done(ok: bool, msg: str):
            self.after(0, self._on_done, ok, msg)

        run_cli_async(argv, done)

    def _on_done(self, ok: bool, msg: str):
        self.btn_run.configure(state="normal")
        self._append_log(msg)
        if ok:
            messagebox.showinfo(APP_TITLE, "Done.")
        else:
            messagebox.showerror(APP_TITLE, "Failed – see log.")


# ----------------------------
# Entrypoint
# ----------------------------

def main():
    root = tk.Tk()
    try:
        root.tk.call("tk", "scaling", 1.2)
    except tk.TclError:
        pass
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()