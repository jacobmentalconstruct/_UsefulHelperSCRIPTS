"""BDVE Embedder Demo — Graphical Interface.

Launch with:  python -m embedder_demo.ui
"""

from __future__ import annotations

import math
import threading
import tkinter as tk
from tkinter import filedialog, ttk
from typing import List

from embedder_demo import core

# ── Colour palette (matches the SVG logo) ────────────────────────────

BG_DARK = "#0d1117"
BG_PANEL = "#161b22"
BG_CARD = "#1c2129"
FG_TEXT = "#c9d1d9"
FG_DIM = "#8b949e"
ACCENT_BLUE = "#58a6ff"
ACCENT_PURPLE = "#bc8cff"
ACCENT_GREEN = "#3fb950"
BORDER = "#30363d"


# =====================================================================
#  Splash screen
# =====================================================================

class SplashScreen(tk.Toplevel):
    """Borderless loading popup that draws the BDVE logo on a canvas."""

    WIDTH = 380
    HEIGHT = 400

    def __init__(self, parent: tk.Tk):
        super().__init__(parent)
        self.overrideredirect(True)
        self.configure(bg=BG_DARK)
        self.attributes("-topmost", True)
        self._center()
        self.canvas = tk.Canvas(
            self,
            width=self.WIDTH,
            height=self.HEIGHT,
            bg=BG_DARK,
            highlightthickness=0,
        )
        self.canvas.pack()
        self._draw_logo()

    # ── positioning ──────────────────────────────────────────────────

    def _center(self):
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - self.WIDTH) // 2
        y = (sh - self.HEIGHT) // 2
        self.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x}+{y}")

    # ── logo drawing (mirrors the SVG structure) ─────────────────────

    def _draw_logo(self):
        c = self.canvas
        cx, cy = self.WIDTH // 2, 160  # centre of the hex

        # Outer hexagon
        hex_r = 110
        hex_pts = self._hex_points(cx, cy, hex_r)
        c.create_polygon(hex_pts, outline=ACCENT_BLUE, fill="", width=1.5)

        # Graph nodes — 6 nodes arranged in inner hex
        inner_r = 70
        node_pts = self._hex_points(cx, cy, inner_r)
        node_radii = [8, 6, 6, 7, 7, 8]

        # Edges — connect adjacent + cross edges
        for i in range(6):
            j = (i + 1) % 6
            x1, y1 = node_pts[i * 2], node_pts[i * 2 + 1]
            x2, y2 = node_pts[j * 2], node_pts[j * 2 + 1]
            c.create_line(x1, y1, x2, y2, fill=ACCENT_BLUE, width=1.2)

        # Cross edges (the semantic bridges)
        cross_pairs = [(0, 3), (1, 4), (2, 5)]
        for a, b in cross_pairs:
            x1, y1 = node_pts[a * 2], node_pts[a * 2 + 1]
            x2, y2 = node_pts[b * 2], node_pts[b * 2 + 1]
            c.create_line(
                x1, y1, x2, y2,
                fill=ACCENT_PURPLE, width=0.8, dash=(4, 4),
            )

        # Draw nodes on top
        for i, r in enumerate(node_radii):
            nx, ny = node_pts[i * 2], node_pts[i * 2 + 1]
            colour = ACCENT_BLUE if i % 2 == 0 else ACCENT_PURPLE
            c.create_oval(
                nx - r, ny - r, nx + r, ny + r,
                fill=colour, outline="",
            )

        # Title text
        c.create_text(
            cx, 290,
            text="BDVE",
            font=("Segoe UI", 28, "bold"),
            fill=ACCENT_BLUE,
        )
        c.create_text(
            cx, 322,
            text="DETERMINISTIC VECTOR EMBEDDINGS",
            font=("Segoe UI", 9),
            fill=FG_DIM,
        )

        # Loading indicator
        self._loading_text = c.create_text(
            cx, 360,
            text="Loading...",
            font=("Segoe UI", 9),
            fill=FG_DIM,
        )

    @staticmethod
    def _hex_points(cx: float, cy: float, r: float) -> List[float]:
        """Return flat list [x0, y0, x1, y1, ...] for a regular hexagon."""
        pts: List[float] = []
        for i in range(6):
            angle = math.radians(60 * i - 90)  # start at top
            pts.append(cx + r * math.cos(angle))
            pts.append(cy + r * math.sin(angle))
        return pts


# =====================================================================
#  Main application window
# =====================================================================

class MainWindow(tk.Tk):
    """Primary demo window with input controls and results display."""

    def __init__(self):
        super().__init__()
        self.title("BDVE Embedder Demo")
        self.configure(bg=BG_DARK)
        self.minsize(900, 620)
        self._center(1000, 700)

        # State — holds results so they persist until cleared
        self._token_result: core.TokenResult | None = None
        self._chunk_result: core.ChunkResult | None = None
        self._embed_results: List[core.EmbeddingResult] = []
        self._reverse_results: List[List[core.NearestToken]] = []

        self._build_styles()
        self._build_toolbar()
        self._build_input_panel()
        self._build_results_panel()
        self._build_statusbar()

        # Auto-load previously trained model if artifacts exist
        if core.load_if_available():
            self._model_indicator.config(text="● Model ready", fg=ACCENT_GREEN)
            self._set_status("Model loaded from saved artifacts — ready.")

    # ── geometry ─────────────────────────────────────────────────────

    def _center(self, w: int, h: int):
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    # ── ttk styles ───────────────────────────────────────────────────

    def _build_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure("Dark.TFrame", background=BG_DARK)
        style.configure("Panel.TFrame", background=BG_PANEL)
        style.configure("Card.TFrame", background=BG_CARD)

        style.configure(
            "Toolbar.TButton",
            background=BG_PANEL,
            foreground=FG_TEXT,
            borderwidth=1,
            focuscolor=ACCENT_BLUE,
            padding=(12, 6),
        )
        style.map(
            "Toolbar.TButton",
            background=[("active", BG_CARD)],
        )
        style.configure(
            "Accent.TButton",
            background=ACCENT_BLUE,
            foreground=BG_DARK,
            borderwidth=0,
            padding=(14, 7),
            font=("Segoe UI", 9, "bold"),
        )
        style.configure(
            "Clear.TButton",
            background="#da3633",
            foreground="#ffffff",
            borderwidth=0,
            padding=(14, 7),
            font=("Segoe UI", 9, "bold"),
        )

        style.configure(
            "Dark.TLabel",
            background=BG_DARK,
            foreground=FG_TEXT,
            font=("Segoe UI", 10),
        )
        style.configure(
            "Header.TLabel",
            background=BG_DARK,
            foreground=ACCENT_BLUE,
            font=("Segoe UI", 11, "bold"),
        )
        style.configure(
            "Dim.TLabel",
            background=BG_DARK,
            foreground=FG_DIM,
            font=("Segoe UI", 9),
        )
        style.configure(
            "Status.TLabel",
            background=BG_PANEL,
            foreground=FG_DIM,
            font=("Segoe UI", 9),
            padding=(8, 4),
        )

    # ── toolbar ──────────────────────────────────────────────────────

    def _build_toolbar(self):
        bar = ttk.Frame(self, style="Panel.TFrame")
        bar.pack(fill=tk.X, padx=0, pady=(0, 1))

        ttk.Label(
            bar, text="  BDVE  ",
            font=("Segoe UI", 12, "bold"),
            foreground=ACCENT_BLUE,
            background=BG_PANEL,
        ).pack(side=tk.LEFT, padx=(8, 16))

        # Train from File button (prominent)
        ttk.Button(
            bar, text="Train from File", command=self._on_train,
            style="Accent.TButton",
        ).pack(side=tk.LEFT, padx=(0, 8), pady=4)

        # Model status indicator
        self._model_indicator = tk.Label(
            bar,
            text="● No model",
            font=("Segoe UI", 9),
            fg=FG_DIM,
            bg=BG_PANEL,
        )
        self._model_indicator.pack(side=tk.LEFT, padx=(0, 16))

        # Separator
        tk.Frame(bar, bg=BORDER, width=1).pack(
            side=tk.LEFT, fill=tk.Y, padx=4, pady=6,
        )

        actions = [
            ("Tokenize", self._on_tokenize),
            ("Chunk", self._on_chunk),
            ("Embed", self._on_embed),
            ("Reverse", self._on_reverse),
        ]
        for label, cmd in actions:
            ttk.Button(
                bar, text=label, command=cmd, style="Toolbar.TButton",
            ).pack(side=tk.LEFT, padx=2, pady=4)

        ttk.Button(
            bar, text="Clear", command=self._on_clear, style="Clear.TButton",
        ).pack(side=tk.RIGHT, padx=8, pady=4)

    # ── input panel (left side) ──────────────────────────────────────

    def _build_input_panel(self):
        wrapper = ttk.Frame(self, style="Dark.TFrame")
        wrapper.pack(side=tk.LEFT, fill=tk.Y, padx=(8, 4), pady=8)

        ttk.Label(wrapper, text="Input Text", style="Header.TLabel").pack(
            anchor=tk.W, pady=(0, 4),
        )

        self._text_input = tk.Text(
            wrapper,
            width=36,
            height=12,
            bg=BG_PANEL,
            fg=FG_TEXT,
            insertbackground=ACCENT_BLUE,
            selectbackground=ACCENT_PURPLE,
            font=("Consolas", 10),
            relief=tk.FLAT,
            borderwidth=0,
            wrap=tk.WORD,
            padx=8,
            pady=8,
        )
        self._text_input.pack(fill=tk.X, pady=(0, 12))
        self._text_input.insert(
            "1.0",
            "The deterministic embedder converts text into "
            "mathematical vectors using pure linear algebra.",
        )

        # Budget control
        budget_frame = ttk.Frame(wrapper, style="Dark.TFrame")
        budget_frame.pack(fill=tk.X, pady=(0, 12))

        ttk.Label(
            budget_frame, text="Token Budget", style="Dark.TLabel",
        ).pack(side=tk.LEFT)

        self._budget_var = tk.IntVar(value=10)
        budget_spin = tk.Spinbox(
            budget_frame,
            from_=2,
            to=512,
            textvariable=self._budget_var,
            width=6,
            bg=BG_PANEL,
            fg=FG_TEXT,
            buttonbackground=BG_CARD,
            font=("Consolas", 10),
            relief=tk.FLAT,
            borderwidth=1,
        )
        budget_spin.pack(side=tk.RIGHT)

        # Quick-action buttons
        ttk.Button(
            wrapper, text="Run Full Pipeline", command=self._on_run_all,
            style="Accent.TButton",
        ).pack(fill=tk.X, pady=(0, 4))

        ttk.Label(
            wrapper,
            text="Tokenize → Chunk → Embed → Reverse",
            style="Dim.TLabel",
        ).pack(anchor=tk.W)

    # ── results panel (right side, scrollable) ───────────────────────

    def _build_results_panel(self):
        container = ttk.Frame(self, style="Dark.TFrame")
        container.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(4, 8), pady=8)

        ttk.Label(container, text="Results", style="Header.TLabel").pack(
            anchor=tk.W, pady=(0, 4),
        )

        # Scrollable canvas
        canvas_frame = ttk.Frame(container, style="Dark.TFrame")
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        self._results_canvas = tk.Canvas(
            canvas_frame, bg=BG_DARK, highlightthickness=0,
        )
        scrollbar = ttk.Scrollbar(
            canvas_frame, orient=tk.VERTICAL, command=self._results_canvas.yview,
        )
        self._results_inner = ttk.Frame(self._results_canvas, style="Dark.TFrame")

        self._results_inner.bind(
            "<Configure>",
            lambda e: self._results_canvas.configure(
                scrollregion=self._results_canvas.bbox("all"),
            ),
        )
        self._canvas_window = self._results_canvas.create_window(
            (0, 0), window=self._results_inner, anchor=tk.NW,
        )
        self._results_canvas.configure(yscrollcommand=scrollbar.set)

        self._results_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Bind canvas resize so inner frame stretches to width
        self._results_canvas.bind("<Configure>", self._on_canvas_resize)

        # Bind mousewheel
        self._results_canvas.bind_all(
            "<MouseWheel>",
            lambda e: self._results_canvas.yview_scroll(
                int(-1 * (e.delta / 120)), "units",
            ),
        )

    def _on_canvas_resize(self, event):
        self._results_canvas.itemconfig(self._canvas_window, width=event.width)

    # ── status bar ───────────────────────────────────────────────────

    def _build_statusbar(self):
        self._status_var = tk.StringVar(value="Ready")
        bar = ttk.Label(
            self, textvariable=self._status_var, style="Status.TLabel",
        )
        bar.pack(side=tk.BOTTOM, fill=tk.X)

    def _set_status(self, msg: str):
        self._status_var.set(msg)
        self.update_idletasks()

    # ── result card builders ─────────────────────────────────────────

    def _add_section(self, title: str) -> tk.Frame:
        """Add a titled section frame to the results panel."""
        frame = tk.Frame(self._results_inner, bg=BG_CARD, padx=12, pady=10)
        frame.pack(fill=tk.X, pady=(0, 6))

        tk.Label(
            frame, text=title,
            font=("Segoe UI", 10, "bold"),
            fg=ACCENT_BLUE, bg=BG_CARD, anchor=tk.W,
        ).pack(fill=tk.X, pady=(0, 6))

        return frame

    def _add_kv(self, parent: tk.Frame, key: str, value: str):
        """Add a key-value row inside a section."""
        row = tk.Frame(parent, bg=BG_CARD)
        row.pack(fill=tk.X, pady=1)
        tk.Label(
            row, text=key, font=("Consolas", 9), fg=FG_DIM, bg=BG_CARD,
            width=14, anchor=tk.W,
        ).pack(side=tk.LEFT)
        tk.Label(
            row, text=value, font=("Consolas", 9), fg=FG_TEXT, bg=BG_CARD,
            anchor=tk.W, wraplength=480,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _add_vector_bar(self, parent: tk.Frame, vector: List[float], label: str = ""):
        """Render a vector as a row of coloured cells (mini heatmap)."""
        row = tk.Frame(parent, bg=BG_CARD)
        row.pack(fill=tk.X, pady=(4, 2))

        if label:
            tk.Label(
                row, text=label, font=("Consolas", 8), fg=FG_DIM, bg=BG_CARD,
                width=12, anchor=tk.W,
            ).pack(side=tk.LEFT)

        bar = tk.Canvas(row, height=18, bg=BG_CARD, highlightthickness=0)
        bar.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Draw after layout so we know the width
        def _draw(event=None):
            bar.delete("all")
            w = bar.winfo_width()
            if not vector or w < 10:
                return
            cell_w = max(w // len(vector), 4)
            v_min = min(vector)
            v_max = max(vector) if max(vector) != v_min else v_min + 1
            for i, v in enumerate(vector):
                t = (v - v_min) / (v_max - v_min)  # 0..1
                # Interpolate blue → purple
                r = int(88 + t * (188 - 88))
                g = int(166 + t * (140 - 166))
                b = int(255 + t * (255 - 255))
                colour = f"#{r:02x}{g:02x}{b:02x}"
                x0 = i * cell_w
                bar.create_rectangle(
                    x0, 0, x0 + cell_w - 1, 18, fill=colour, outline="",
                )

        bar.bind("<Configure>", _draw)

    def _add_token_pills(self, parent: tk.Frame, symbols: List[str]):
        """Render tokens as coloured pill labels in a flow layout."""
        flow = tk.Frame(parent, bg=BG_CARD)
        flow.pack(fill=tk.X, pady=(2, 4))

        for sym in symbols:
            colour = ACCENT_PURPLE if sym == "</w>" else ACCENT_BLUE
            pill = tk.Label(
                flow,
                text=f" {sym} ",
                font=("Consolas", 9),
                fg=BG_DARK,
                bg=colour,
                padx=4,
                pady=1,
            )
            pill.pack(side=tk.LEFT, padx=(0, 3), pady=2)

    # ── action handlers ──────────────────────────────────────────────

    def _get_text(self) -> str:
        return self._text_input.get("1.0", tk.END).strip()

    def _on_tokenize(self):
        text = self._get_text()
        if not text:
            self._set_status("Enter some text first.")
            return

        self._set_status("Tokenizing...")
        self._token_result = core.tokenize(text)

        sec = self._add_section("Tokenize — Text → Tokens")
        self._add_kv(sec, "input", text[:80] + ("..." if len(text) > 80 else ""))
        self._add_kv(sec, "token count", str(len(self._token_result.symbols)))
        self._add_kv(sec, "token IDs", str(self._token_result.token_ids))
        self._add_token_pills(sec, self._token_result.symbols)

        self._set_status(
            f"Tokenized: {len(self._token_result.symbols)} tokens"
        )

    def _on_chunk(self):
        text = self._get_text()
        budget = self._budget_var.get()
        if not text:
            self._set_status("Enter some text first.")
            return

        self._set_status(f"Chunking with budget={budget}...")
        self._chunk_result = core.chunk(text, budget)

        sec = self._add_section(
            f"Chunk — {self._chunk_result.total_tokens} tokens → "
            f"{len(self._chunk_result.hunks)} hunks (budget {budget})"
        )

        for hunk in self._chunk_result.hunks:
            hunk_frame = tk.Frame(sec, bg=BG_PANEL, padx=8, pady=6)
            hunk_frame.pack(fill=tk.X, pady=(0, 4))

            tk.Label(
                hunk_frame,
                text=f"Hunk {hunk.index}  ({hunk.token_count} tokens)",
                font=("Segoe UI", 9, "bold"),
                fg=ACCENT_GREEN, bg=BG_PANEL,
            ).pack(anchor=tk.W)
            self._add_token_pills(hunk_frame, hunk.symbols)

        self._set_status(
            f"Chunked: {len(self._chunk_result.hunks)} hunks"
        )

    def _on_embed(self):
        if not self._chunk_result:
            self._set_status("Run Chunk first to create hunks.")
            return

        self._set_status("Embedding hunks...")
        self._embed_results.clear()

        sec = self._add_section(
            f"Embed — {len(self._chunk_result.hunks)} hunks → vectors"
        )

        for hunk in self._chunk_result.hunks:
            res = core.embed_hunk(hunk)
            self._embed_results.append(res)

            hunk_frame = tk.Frame(sec, bg=BG_PANEL, padx=8, pady=6)
            hunk_frame.pack(fill=tk.X, pady=(0, 4))

            tk.Label(
                hunk_frame,
                text=f"Hunk {res.hunk_index}  →  {res.dimensions}d vector",
                font=("Segoe UI", 9, "bold"),
                fg=ACCENT_GREEN, bg=BG_PANEL,
            ).pack(anchor=tk.W)

            self._add_token_pills(hunk_frame, res.symbols)
            self._add_vector_bar(hunk_frame, res.vector, label="embedding")

            vals = "  ".join(f"{v:+.4f}" for v in res.vector[:8])
            tk.Label(
                hunk_frame,
                text=f"[{vals}{'  ...' if len(res.vector) > 8 else ''}]",
                font=("Consolas", 8),
                fg=FG_DIM, bg=BG_PANEL, anchor=tk.W,
            ).pack(fill=tk.X)

            # Force progressive display
            self.update_idletasks()

        self._set_status(
            f"Embedded: {len(self._embed_results)} vectors "
            f"({self._embed_results[0].dimensions}d)"
        )

    def _on_reverse(self):
        if not self._embed_results:
            self._set_status("Run Embed first to create vectors.")
            return

        self._set_status("Reversing vectors → nearest tokens...")
        self._reverse_results.clear()

        sec = self._add_section("Reverse — vectors → nearest tokens")

        for emb in self._embed_results:
            nearest = core.reverse_vector(emb.vector, k=5)
            self._reverse_results.append(nearest)

            hunk_frame = tk.Frame(sec, bg=BG_PANEL, padx=8, pady=6)
            hunk_frame.pack(fill=tk.X, pady=(0, 4))

            tk.Label(
                hunk_frame,
                text=f"Hunk {emb.hunk_index} — top 5 nearest tokens",
                font=("Segoe UI", 9, "bold"),
                fg=ACCENT_GREEN, bg=BG_PANEL,
            ).pack(anchor=tk.W)

            for nt in nearest:
                row = tk.Frame(hunk_frame, bg=BG_PANEL)
                row.pack(fill=tk.X, pady=1)

                # Similarity bar
                bar_w = int(nt.similarity * 120)
                tk.Label(
                    row,
                    text=f" {nt.symbol} ",
                    font=("Consolas", 9),
                    fg=BG_DARK, bg=ACCENT_BLUE,
                    padx=4,
                ).pack(side=tk.LEFT, padx=(0, 6))

                bar_canvas = tk.Canvas(
                    row, width=130, height=14, bg=BG_CARD, highlightthickness=0,
                )
                bar_canvas.pack(side=tk.LEFT, padx=(0, 6))
                bar_canvas.create_rectangle(
                    0, 0, bar_w, 14, fill=ACCENT_PURPLE, outline="",
                )

                tk.Label(
                    row,
                    text=f"cos = {nt.similarity:+.4f}",
                    font=("Consolas", 8),
                    fg=FG_DIM, bg=BG_PANEL,
                ).pack(side=tk.LEFT)

            self.update_idletasks()

        self._set_status(
            f"Reversed: {len(self._reverse_results)} vectors"
        )

    # ── training handler ─────────────────────────────────────────────

    def _on_train(self):
        """Open file picker and train the BDVE model in a background thread."""
        path = filedialog.askopenfilename(
            title="Select training file",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return

        self._set_status("Training...")
        self._model_indicator.config(text="● Training...", fg="#e3b341")

        def _run():
            try:
                core.train_from_file(
                    path,
                    on_progress=lambda msg: self.after(0, self._set_status, msg),
                )
                self.after(0, self._training_complete)
            except Exception as e:
                self.after(0, self._set_status, f"Training failed: {e}")
                self.after(
                    0,
                    lambda: self._model_indicator.config(
                        text="● Error", fg="#da3633",
                    ),
                )

        threading.Thread(target=_run, daemon=True).start()

    def _training_complete(self):
        """Called on the main thread when training finishes successfully."""
        self._model_indicator.config(text="● Model ready", fg=ACCENT_GREEN)
        self._set_status("Training complete — model ready. Run the pipeline!")

    def _on_clear(self):
        """Clear all results from the display."""
        for w in self._results_inner.winfo_children():
            w.destroy()
        self._token_result = None
        self._chunk_result = None
        self._embed_results.clear()
        self._reverse_results.clear()
        self._set_status("Cleared.")

    def _on_run_all(self):
        """Run the full pipeline: tokenize → chunk → embed → reverse."""
        self._on_clear()
        self._on_tokenize()
        self._on_chunk()
        self._on_embed()
        self._on_reverse()
        self._set_status("Full pipeline complete.")


# =====================================================================
#  Entry point
# =====================================================================

def main():
    root = MainWindow()
    root.withdraw()  # hide main window during splash

    splash = SplashScreen(root)
    splash.update()

    # Show splash for 2 seconds, then transition
    def _finish_splash():
        splash.destroy()
        root.deiconify()

    root.after(2000, _finish_splash)
    root.mainloop()


if __name__ == "__main__":
    main()
