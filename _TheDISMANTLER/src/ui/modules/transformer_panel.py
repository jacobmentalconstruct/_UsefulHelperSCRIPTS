"""
Transformer Panel – UI for the Modular Transformation Engine.
Allows users to parse monolithic files and extract their logic
into the Dismantler structure.
"""
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import threading
from theme import THEME
from ui.modules._buttons import AccentButton, ToolbarButton


class TransformerPanel(tk.Toplevel):
    """
    Interactive transformer UI.
    Steps:
    1. Select a monolithic file
    2. Choose extraction strategy (manual or auto)
    3. Review extraction plan
    4. Execute with optional dry-run
    """

    def __init__(self, parent, backend=None):
        super().__init__(parent)
        self.backend = backend
        self.title("Modular Transformation Engine")
        self.geometry("900x700")
        self.configure(bg=THEME["bg"])

        self._selected_file = None
        self._extraction_plan = None

        self._build_ui()

    def _build_ui(self):
        """Build the three-panel interface."""
        # Header
        header = tk.Label(
            self,
            text="DISMANTLER  //  Monolith Extraction Engine",
            bg=THEME["bg"],
            fg=THEME["accent"],
            font=THEME["font_interface_bold"],
            anchor="w",
            padx=10,
        )
        header.pack(fill="x", pady=(8, 0))

        # Main container
        main = tk.Frame(self, bg=THEME["bg"])
        main.pack(fill="both", expand=True, padx=10, pady=8)

        # --- Step 1: File Selection ---
        self._build_file_selection(main)

        # --- Step 2: Strategy Selection ---
        self._build_strategy_selection(main)

        # --- Step 3: Extraction Plan Preview ---
        self._build_plan_preview(main)

        # --- Action Buttons ---
        self._build_action_buttons(main)

    def _build_file_selection(self, parent):
        frame = tk.Frame(parent, bg=THEME["bg2"], relief="flat")
        frame.pack(fill="x", pady=(0, 8))

        tk.Label(
            frame,
            text="STEP 1: Select Monolithic File",
            bg=THEME["bg2"],
            fg=THEME["accent"],
            font=THEME["font_interface_bold"],
            anchor="w",
        ).pack(fill="x", padx=8, pady=(6, 2))

        sub = tk.Frame(frame, bg=THEME["bg2"])
        sub.pack(fill="x", padx=8, pady=(0, 6))

        self.file_label = tk.Label(
            sub,
            text="No file selected",
            bg=THEME["bg2"],
            fg=THEME["fg_dim"],
            font=THEME["font_interface_small"],
            anchor="w",
        )
        self.file_label.pack(fill="x", side="left", expand=True)

        ToolbarButton(sub, text="Browse", command=self._select_file).pack(side="right", padx=(4, 0))

    def _build_strategy_selection(self, parent):
        frame = tk.Frame(parent, bg=THEME["bg2"], relief="flat")
        frame.pack(fill="x", pady=(0, 8))

        tk.Label(
            frame,
            text="STEP 2: Choose Extraction Strategy",
            bg=THEME["bg2"],
            fg=THEME["accent"],
            font=THEME["font_interface_bold"],
            anchor="w",
        ).pack(fill="x", padx=8, pady=(6, 2))

        sub = tk.Frame(frame, bg=THEME["bg2"])
        sub.pack(fill="x", padx=8, pady=(0, 6))

        self.strategy = tk.StringVar(value="auto")

        tk.Radiobutton(
            sub,
            text="Auto-detect (uses heuristics & patterns)",
            variable=self.strategy,
            value="auto",
            bg=THEME["bg2"],
            fg=THEME["fg"],
            selectcolor=THEME["accent"],
            activebackground=THEME["bg2"],
        ).pack(anchor="w")

        tk.Radiobutton(
            sub,
            text="Manual tags (requires # <EXTRACT_TO:...> comments)",
            variable=self.strategy,
            value="manual",
            bg=THEME["bg2"],
            fg=THEME["fg"],
            selectcolor=THEME["accent"],
            activebackground=THEME["bg2"],
        ).pack(anchor="w")

    def _build_plan_preview(self, parent):
        frame = tk.Frame(parent, bg=THEME["bg2"], relief="flat")
        frame.pack(fill="both", expand=True, pady=(0, 8))

        tk.Label(
            frame,
            text="STEP 3: Extraction Plan Preview",
            bg=THEME["bg2"],
            fg=THEME["accent"],
            font=THEME["font_interface_bold"],
            anchor="w",
        ).pack(fill="x", padx=8, pady=(6, 2))

        self.plan_text = scrolledtext.ScrolledText(
            frame,
            bg=THEME["bg3"],
            fg=THEME["fg"],
            font=THEME["font_code_small"],
            height=12,
            relief="flat",
            padx=6,
            pady=4,
        )
        self.plan_text.pack(fill="both", expand=True, padx=8, pady=(0, 6))
        self.plan_text.insert("1.0", "Plan will appear here after analysis...")
        self.plan_text.config(state="disabled")

    def _build_action_buttons(self, parent):
        frame = tk.Frame(parent, bg=THEME["bg"])
        frame.pack(fill="x")

        self.dry_run_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            frame,
            text="Dry-run (preview without writing)",
            variable=self.dry_run_var,
            bg=THEME["bg"],
            fg=THEME["fg"],
            selectcolor=THEME["bg2"],
            activebackground=THEME["bg"],
        ).pack(side="left")

        AccentButton(frame, text="Analyze", command=self._analyze).pack(side="right", padx=(4, 0))
        AccentButton(frame, text="Extract", command=self._execute_extraction).pack(side="right", padx=4)

    # ── handlers ────────────────────────────────────────────

    def _select_file(self):
        path = filedialog.askopenfilename(
            filetypes=[("Python", "*.py"), ("All Files", "*.*")],
            title="Select Monolithic File",
        )
        if path:
            self._selected_file = path
            self.file_label.config(text=path)

    def _analyze(self):
        if not self._selected_file:
            messagebox.showwarning("No File", "Please select a file first.")
            return

        if not self.backend:
            messagebox.showerror("Error", "No backend available.")
            return

        self.plan_text.config(state="normal")
        self.plan_text.delete("1.0", "end")
        self.plan_text.insert("1.0", "Analyzing...\n")
        self.plan_text.config(state="disabled")

        # Run in background thread
        threading.Thread(target=self._analyze_background, daemon=True).start()

    def _analyze_background(self):
        try:
            # Request analysis from transformer controller
            result = self.backend.execute_task({
                "system": "transformer",
                "action": "guide",
                "file": self._selected_file,
            })

            if result.get("status") == "ok":
                guide = result.get("guide", "No guide generated")
                self._extraction_plan = guide
                self.after(0, lambda: self._update_plan_display(guide))
            else:
                error = result.get("message", "Unknown error")
                self.after(0, lambda: self._update_plan_display(f"Error: {error}"))
        except Exception as e:
            self.after(0, lambda: self._update_plan_display(f"Failed: {str(e)}"))

    def _update_plan_display(self, text):
        self.plan_text.config(state="normal")
        self.plan_text.delete("1.0", "end")
        self.plan_text.insert("1.0", text)
        self.plan_text.config(state="disabled")

    def _execute_extraction(self):
        if not self._selected_file:
            messagebox.showwarning("No File", "Please select a file first.")
            return

        if not self.backend:
            messagebox.showerror("Error", "No backend available.")
            return

        strategy = self.strategy.get()
        dry_run = self.dry_run_var.get()

        action = "extract_auto" if strategy == "auto" else "extract_tagged"

        self.plan_text.config(state="normal")
        self.plan_text.delete("1.0", "end")
        self.plan_text.insert("1.0", "Extracting...\n")
        self.plan_text.config(state="disabled")

        threading.Thread(
            target=self._extract_background,
            args=(action, dry_run),
            daemon=True,
        ).start()

    def _extract_background(self, action, dry_run):
        try:
            result = self.backend.execute_task({
                "system": "transformer",
                "action": action,
                "file": self._selected_file,
                "dry_run": dry_run,
            })

            status = result.get("status", "error")
            message = result.get("message", "No message")
            blocks = result.get("blocks", 0)

            summary = f"Status: {status}\n"
            if blocks:
                summary += f"Blocks processed: {blocks}\n"
            summary += f"\n{message}"

            self.after(0, lambda: self._update_plan_display(summary))

            if status == "ok" and not dry_run:
                self.after(
                    0,
                    lambda: messagebox.showinfo(
                        "Extraction Complete",
                        "Files have been written successfully!",
                    ),
                )
        except Exception as e:
            self.after(0, lambda: self._update_plan_display(f"Failed: {str(e)}"))
