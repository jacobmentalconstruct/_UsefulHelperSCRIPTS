"""
Standalone Scratchpad Window — A Notepad++-style editor for shared scratchpad content.
Singleton managed by app.py, toggled from any Cell.

Features:
- Pad/Section selector with create-new support
- Full text editor with debounced auto-save
- AI instruction bar with streamed inference
- Inline diff preview (red/green) with Accept/Reject
- Undo/Redo stack for AI edits
"""

import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
import difflib
import threading


class ScratchpadWindow:
    """
    A Toplevel window wrapping the shared ScratchpadMS.
    Withdraw/deiconify pattern — never destroyed until app exit.
    """

    def __init__(self, root, colors, scratchpad_ms, engine, bus=None):
        """
        Args:
            root: The Tk root (or any parent for Toplevel).
            colors: Theme color dict from AppShell.
            scratchpad_ms: ScratchpadMS instance (shared DB).
            engine: IngestEngineMS for AI operations.
            bus: Optional SignalBusMS for theme/visibility signals.
        """
        self.root = root
        self.colors = colors
        self.scratchpad = scratchpad_ms
        self.engine = engine
        self.bus = bus

        # State
        self._current_pad = None
        self._current_section = "default"
        self._save_timer = None
        self._undo_stack = []
        self._redo_stack = []
        self._ai_draft_text = None
        self._ai_running = False

        # Build the window (hidden initially)
        self.win = tk.Toplevel(root)
        self.win.title("Scratchpad")
        self.win.geometry("750x650")
        self.win.configure(bg=colors.get('background', '#1e1e1e'))
        self.win.protocol("WM_DELETE_WINDOW", self.hide)
        self.win.withdraw()

        self._build_ui()
        self._refresh_pads()

        # Subscribe to theme updates
        if self.bus:
            self.bus.subscribe("theme_updated", self._on_theme_updated)

    # ─── UI Construction ──────────────────────────────────────────────

    def _build_ui(self):
        c = self.colors

        # --- Top bar: Pad/Section selectors ---
        top = tk.Frame(self.win, bg=c.get('panel_bg', '#252526'))
        top.pack(fill='x', padx=6, pady=(6, 2))

        tk.Label(top, text="Pad:", bg=c.get('panel_bg'), fg=c.get('foreground'),
                 font=c.get('font_main', ('Segoe UI', 10))).pack(side='left', padx=(4, 2))

        self.pad_var = tk.StringVar()
        self.pad_combo = ttk.Combobox(top, textvariable=self.pad_var, state='readonly', width=20)
        self.pad_combo.pack(side='left', padx=2)
        self.pad_combo.bind("<<ComboboxSelected>>", self._on_pad_selected)

        tk.Button(top, text="+", width=2, bg=c.get('button_bg', '#0e639c'),
                  fg=c.get('button_fg', '#fff'), relief='flat', bd=0,
                  command=self._new_pad).pack(side='left', padx=2)

        tk.Label(top, text="Sec:", bg=c.get('panel_bg'), fg=c.get('foreground'),
                 font=c.get('font_main', ('Segoe UI', 10))).pack(side='left', padx=(12, 2))

        self.sec_var = tk.StringVar(value="default")
        self.sec_combo = ttk.Combobox(top, textvariable=self.sec_var, state='readonly', width=14)
        self.sec_combo.pack(side='left', padx=2)
        self.sec_combo.bind("<<ComboboxSelected>>", self._on_section_selected)

        tk.Button(top, text="+", width=2, bg=c.get('button_bg', '#0e639c'),
                  fg=c.get('button_fg', '#fff'), relief='flat', bd=0,
                  command=self._new_section).pack(side='left', padx=2)

        # Undo / Redo buttons
        self.btn_undo = tk.Button(top, text="Undo", width=5, relief='flat', bd=0,
                                  bg=c.get('panel_bg'), fg=c.get('foreground'),
                                  state='disabled', command=self._undo)
        self.btn_undo.pack(side='right', padx=2)

        self.btn_redo = tk.Button(top, text="Redo", width=5, relief='flat', bd=0,
                                  bg=c.get('panel_bg'), fg=c.get('foreground'),
                                  state='disabled', command=self._redo)
        self.btn_redo.pack(side='right', padx=2)

        # --- Main editor ---
        editor_frame = tk.Frame(self.win, bg=c.get('background'))
        editor_frame.pack(fill='both', expand=True, padx=6, pady=2)

        self.editor = tk.Text(
            editor_frame,
            wrap='word',
            bg=c.get('entry_bg', '#1e1e1e'),
            fg=c.get('entry_fg', '#d4d4d4'),
            insertbackground=c.get('foreground', '#d4d4d4'),
            selectbackground=c.get('select_bg', '#264f78'),
            selectforeground=c.get('select_fg', '#ffffff'),
            font=c.get('font_mono', ('Consolas', 11)),
            relief='flat', bd=0,
            undo=True
        )
        editor_scroll = tk.Scrollbar(editor_frame, command=self.editor.yview)
        self.editor.configure(yscrollcommand=editor_scroll.set)
        editor_scroll.pack(side='right', fill='y')
        self.editor.pack(fill='both', expand=True)
        self.editor.bind("<KeyRelease>", self._on_editor_key)

        # --- Diff preview (hidden by default) ---
        self.diff_frame = tk.Frame(self.win, bg=c.get('panel_bg', '#252526'))
        # Not packed until AI runs

        tk.Label(self.diff_frame, text="AI Diff Preview", anchor='w',
                 bg=c.get('panel_bg'), fg=c.get('accent', '#007acc'),
                 font=('Segoe UI', 10, 'bold')).pack(fill='x', padx=6, pady=(4, 0))

        diff_editor_frame = tk.Frame(self.diff_frame, bg=c.get('background'))
        diff_editor_frame.pack(fill='both', expand=True, padx=6, pady=2)

        self.diff_view = tk.Text(
            diff_editor_frame,
            wrap='word', height=10,
            bg=c.get('entry_bg', '#1e1e1e'),
            fg=c.get('entry_fg', '#d4d4d4'),
            font=c.get('font_mono', ('Consolas', 11)),
            relief='flat', bd=0,
            state='disabled'
        )
        diff_scroll = tk.Scrollbar(diff_editor_frame, command=self.diff_view.yview)
        self.diff_view.configure(yscrollcommand=diff_scroll.set)
        diff_scroll.pack(side='right', fill='y')
        self.diff_view.pack(fill='both', expand=True)

        # Diff tags
        self.diff_view.tag_configure("diff_add", background="#1e3a1e", foreground="#89d185")
        self.diff_view.tag_configure("diff_del", background="#3a1e1e", foreground="#f44747")
        self.diff_view.tag_configure("diff_header", foreground="#666666")

        # Accept / Reject buttons
        diff_btns = tk.Frame(self.diff_frame, bg=c.get('panel_bg'))
        diff_btns.pack(fill='x', padx=6, pady=(0, 4))

        self.btn_accept = tk.Button(diff_btns, text="Accept", width=10,
                                    bg=c.get('success', '#89d185'), fg='#1e1e1e',
                                    relief='flat', bd=0, command=self._accept_diff)
        self.btn_accept.pack(side='left', padx=4)

        self.btn_reject = tk.Button(diff_btns, text="Reject", width=10,
                                    bg=c.get('error', '#f44747'), fg='#ffffff',
                                    relief='flat', bd=0, command=self._reject_diff)
        self.btn_reject.pack(side='left', padx=4)

        # --- AI instruction bar ---
        ai_bar = tk.Frame(self.win, bg=c.get('panel_bg', '#252526'))
        ai_bar.pack(fill='x', padx=6, pady=(2, 6))

        tk.Label(ai_bar, text="AI:", bg=c.get('panel_bg'), fg=c.get('foreground'),
                 font=c.get('font_main', ('Segoe UI', 10))).pack(side='left', padx=(4, 2))

        self.ai_instruction = tk.Entry(
            ai_bar,
            bg=c.get('entry_bg', '#1e1e1e'),
            fg=c.get('entry_fg', '#d4d4d4'),
            insertbackground=c.get('foreground'),
            font=c.get('font_main', ('Segoe UI', 10)),
            relief='flat', bd=0
        )
        self.ai_instruction.pack(side='left', fill='x', expand=True, padx=4, ipady=3)
        self.ai_instruction.bind("<Return>", lambda e: self._run_ai())

        tk.Label(ai_bar, text="Model:", bg=c.get('panel_bg'), fg=c.get('foreground'),
                 font=c.get('font_main', ('Segoe UI', 10))).pack(side='left', padx=(8, 2))

        self.model_var = tk.StringVar()
        self.model_combo = ttk.Combobox(ai_bar, textvariable=self.model_var, state='readonly', width=16)
        self.model_combo.pack(side='left', padx=2)

        self.btn_run_ai = tk.Button(ai_bar, text="Run AI", width=8,
                                    bg=c.get('accent', '#007acc'), fg=c.get('button_fg', '#fff'),
                                    relief='flat', bd=0, command=self._run_ai)
        self.btn_run_ai.pack(side='left', padx=(4, 4))

        # Status
        self.status_var = tk.StringVar(value="Ready")
        self.status_label = tk.Label(
            self.win, textvariable=self.status_var, anchor='w',
            bg=c.get('background'), fg=c.get('foreground', '#888'),
            font=('Segoe UI', 9)
        )
        self.status_label.pack(fill='x', padx=8, pady=(0, 4))

        # Populate model list
        self._refresh_models()

    # ─── Show / Hide ──────────────────────────────────────────────────

    def show(self):
        self._refresh_pads()
        self._refresh_models()
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()
        if self.bus:
            self.bus.emit("scratchpad_visibility_changed", True)

    def hide(self):
        self._save_now()
        self.win.withdraw()
        if self.bus:
            self.bus.emit("scratchpad_visibility_changed", False)

    # ─── Pad / Section management ─────────────────────────────────────

    def _refresh_pads(self):
        pads = self.scratchpad.list_pads()
        names = [p.name for p in pads]
        self.pad_combo['values'] = names
        if names:
            if self._current_pad not in names:
                self._current_pad = names[0]
            self.pad_var.set(self._current_pad)
            self._refresh_sections()
        else:
            self.pad_var.set("")
            self.sec_combo['values'] = []
            self.editor.delete("1.0", "end")

    def _refresh_sections(self):
        if not self._current_pad:
            return
        sections = self.scratchpad.get_sections(self._current_pad)
        if not sections:
            sections = ["default"]
        self.sec_combo['values'] = sections
        if self._current_section not in sections:
            self._current_section = sections[0]
        self.sec_var.set(self._current_section)
        self._load_content()

    def _load_content(self):
        if not self._current_pad:
            return
        entries = self.scratchpad.read(self._current_pad, self._current_section)
        text = "\n\n".join(e.content for e in entries) if entries else ""
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", text)
        self.editor.edit_reset()  # Clear Tk's internal undo
        self.status_var.set(f"Loaded: {self._current_pad}/{self._current_section}")

    def _on_pad_selected(self, event=None):
        self._save_now()
        self._current_pad = self.pad_var.get()
        self._current_section = "default"
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._update_undo_buttons()
        self._refresh_sections()

    def _on_section_selected(self, event=None):
        self._save_now()
        self._current_section = self.sec_var.get()
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._update_undo_buttons()
        self._load_content()

    def _new_pad(self):
        name = simpledialog.askstring("New Pad", "Scratchpad name:", parent=self.win)
        if not name or not name.strip():
            return
        name = name.strip()
        self.scratchpad.create(name)
        self._current_pad = name
        self._current_section = "default"
        self._refresh_pads()

    def _new_section(self):
        if not self._current_pad:
            messagebox.showwarning("No Pad", "Select or create a pad first.", parent=self.win)
            return
        name = simpledialog.askstring("New Section", "Section name:", parent=self.win)
        if not name or not name.strip():
            return
        name = name.strip()
        # Write an empty entry to create the section
        self.scratchpad.replace_content(self._current_pad, "", section=name)
        self._current_section = name
        self._refresh_sections()

    # ─── Auto-save (debounced) ────────────────────────────────────────

    def _on_editor_key(self, event=None):
        if self._save_timer:
            self.win.after_cancel(self._save_timer)
        self._save_timer = self.win.after(1500, self._save_now)

    def _save_now(self):
        if not self._current_pad:
            return
        content = self.editor.get("1.0", "end-1c")
        self.scratchpad.replace_content(
            self._current_pad, content,
            author="user", section=self._current_section
        )
        self.status_var.set(f"Saved: {self._current_pad}/{self._current_section}")

    # ─── AI Diff Workflow ─────────────────────────────────────────────

    def _run_ai(self):
        if self._ai_running:
            return
        instruction = self.ai_instruction.get().strip()
        if not instruction:
            self.status_var.set("Enter an instruction for the AI.")
            return
        if not self._current_pad:
            self.status_var.set("Select or create a pad first.")
            return

        # Save current content first
        self._save_now()

        model = self.model_var.get() or None
        self._ai_running = True
        self.btn_run_ai.configure(state='disabled')
        self.status_var.set("AI is thinking...")

        def worker():
            try:
                result = self.scratchpad.ai_draft(
                    self._current_pad, instruction,
                    model=model, section=self._current_section
                )
                self.win.after(0, lambda: self._show_diff(result))
            except Exception as e:
                self.win.after(0, lambda: self._ai_error(str(e)))

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def _ai_error(self, msg):
        self._ai_running = False
        self.btn_run_ai.configure(state='normal')
        self.status_var.set(f"AI Error: {msg}")

    def _show_diff(self, ai_text):
        self._ai_running = False
        self.btn_run_ai.configure(state='normal')
        self._ai_draft_text = ai_text

        current = self.editor.get("1.0", "end-1c")
        current_lines = current.splitlines(keepends=True)
        ai_lines = ai_text.splitlines(keepends=True)

        diff = list(difflib.unified_diff(
            current_lines, ai_lines,
            fromfile="current", tofile="ai_draft", lineterm=""
        ))

        # Render diff
        self.diff_view.configure(state='normal')
        self.diff_view.delete("1.0", "end")

        if not diff:
            self.diff_view.insert("end", "(No changes — AI output matches current content.)")
            self._ai_draft_text = None
        else:
            for line in diff:
                clean = line.rstrip('\n')
                if clean.startswith("+++") or clean.startswith("---"):
                    self.diff_view.insert("end", clean + "\n", "diff_header")
                elif clean.startswith("@@"):
                    self.diff_view.insert("end", clean + "\n", "diff_header")
                elif clean.startswith("+"):
                    self.diff_view.insert("end", clean + "\n", "diff_add")
                elif clean.startswith("-"):
                    self.diff_view.insert("end", clean + "\n", "diff_del")
                else:
                    self.diff_view.insert("end", clean + "\n")

        self.diff_view.configure(state='disabled')

        # Show diff panel
        self.diff_frame.pack(fill='both', expand=True, padx=6, pady=2, before=self._get_ai_bar())
        self.status_var.set("Review the AI changes below. Accept or Reject.")

    def _get_ai_bar(self):
        """Returns the AI bar frame (the frame packed at the bottom)."""
        # The AI bar is the second-to-last child of self.win
        children = self.win.pack_slaves()
        # AI bar is packed after editor, diff is inserted before it
        for child in children:
            if hasattr(child, 'pack_info'):
                info = child.pack_info()
        # Return status_label's predecessor
        return self.status_label

    def _accept_diff(self):
        if self._ai_draft_text is None:
            self._close_diff_panel()
            return

        # Push current content to undo stack
        current = self.editor.get("1.0", "end-1c")
        self._undo_stack.append(current)
        self._redo_stack.clear()

        # Apply AI text
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", self._ai_draft_text)
        self._save_now()

        self._ai_draft_text = None
        self._close_diff_panel()
        self._update_undo_buttons()
        self.status_var.set("AI changes accepted and saved.")

    def _reject_diff(self):
        self._ai_draft_text = None
        self._close_diff_panel()
        self.status_var.set("AI changes rejected.")

    def _close_diff_panel(self):
        self.diff_frame.pack_forget()

    # ─── Undo / Redo ──────────────────────────────────────────────────

    def _undo(self):
        if not self._undo_stack:
            return
        current = self.editor.get("1.0", "end-1c")
        self._redo_stack.append(current)
        prev = self._undo_stack.pop()
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", prev)
        self._save_now()
        self._update_undo_buttons()
        self.status_var.set("Undo applied.")

    def _redo(self):
        if not self._redo_stack:
            return
        current = self.editor.get("1.0", "end-1c")
        self._undo_stack.append(current)
        nxt = self._redo_stack.pop()
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", nxt)
        self._save_now()
        self._update_undo_buttons()
        self.status_var.set("Redo applied.")

    def _update_undo_buttons(self):
        self.btn_undo.configure(state='normal' if self._undo_stack else 'disabled')
        self.btn_redo.configure(state='normal' if self._redo_stack else 'disabled')

    # ─── Models ───────────────────────────────────────────────────────

    def _refresh_models(self):
        try:
            models = self.engine.get_available_models() if self.engine else []
        except Exception:
            models = []
        if not models:
            models = ["No Models Found"]
        self.model_combo['values'] = models
        if models:
            self.model_var.set(models[0])

    # ─── Theming ──────────────────────────────────────────────────────

    def _on_theme_updated(self, new_colors):
        if not new_colors:
            return
        self.colors = new_colors
        self.refresh_theme()

    def refresh_theme(self):
        c = self.colors
        bg = c.get('background', '#1e1e1e')
        fg = c.get('foreground', '#d4d4d4')
        panel = c.get('panel_bg', '#252526')
        entry_bg = c.get('entry_bg', bg)
        entry_fg = c.get('entry_fg', fg)
        accent = c.get('accent', '#007acc')
        btn_bg = c.get('button_bg', '#0e639c')
        btn_fg = c.get('button_fg', '#fff')
        select_bg = c.get('select_bg', '#264f78')
        select_fg = c.get('select_fg', '#fff')
        success = c.get('success', '#89d185')
        error = c.get('error', '#f44747')

        self.win.configure(bg=bg)

        # Editor
        self.editor.configure(bg=entry_bg, fg=entry_fg, insertbackground=fg,
                              selectbackground=select_bg, selectforeground=select_fg)

        # Diff view
        self.diff_view.configure(bg=entry_bg, fg=entry_fg)
        # Update diff tag colors based on theme
        is_dark = bg.lower() in ('#1e1e1e', '#252526') or bg < '#808080'
        if is_dark:
            self.diff_view.tag_configure("diff_add", background="#1e3a1e", foreground="#89d185")
            self.diff_view.tag_configure("diff_del", background="#3a1e1e", foreground="#f44747")
        else:
            self.diff_view.tag_configure("diff_add", background="#d4edda", foreground="#155724")
            self.diff_view.tag_configure("diff_del", background="#f8d7da", foreground="#721c24")
        self.diff_view.tag_configure("diff_header", foreground="#888888")

        # AI instruction entry
        self.ai_instruction.configure(bg=entry_bg, fg=entry_fg, insertbackground=fg)

        # Status
        self.status_label.configure(bg=bg, fg=fg)

        # Buttons
        self.btn_run_ai.configure(bg=accent, fg=btn_fg)
        self.btn_accept.configure(bg=success, fg='#1e1e1e')
        self.btn_reject.configure(bg=error, fg='#ffffff')
        self.btn_undo.configure(bg=panel, fg=fg)
        self.btn_redo.configure(bg=panel, fg=fg)

        # All frame backgrounds
        for child in self.win.winfo_children():
            if isinstance(child, tk.Frame):
                try:
                    child.configure(bg=panel if child != self.editor.master else bg)
                except tk.TclError:
                    pass
            if isinstance(child, tk.Label):
                try:
                    child.configure(bg=bg if child == self.status_label else panel, fg=fg)
                except tk.TclError:
                    pass
