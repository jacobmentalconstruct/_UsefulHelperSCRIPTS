"""
Refinement Panel – AI-assisted iterative plan refinement UI.
Displays a dual-pane view (current plan | AI streaming output)
with pass indicators and approve/retry/auto-accept/cancel controls.
Stateless UI: all refinement logic is in backend/modules/refinement_engine.py.
"""
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
from theme import THEME
from ui.modules._buttons import AccentButton, ToolbarButton
from ui.modules.model_selector import ModelSelector


class RefinementPanel(tk.Toplevel):
    """
    AI Plan Refinement window.
    Iterates over an extraction plan with an AI model,
    letting the user approve/retry/auto-accept/cancel at each step.
    """

    def __init__(self, parent, backend, file_path, initial_plan):
        super().__init__(parent)
        self.backend = backend
        self.file_path = file_path
        self.initial_plan = initial_plan

        self._session_id = None
        self._current_pass = 0
        self._auto_accept = False
        self._running = False

        self.title("AI Plan Refinement")
        self.geometry("1000x750")
        self.configure(bg=THEME["bg"])
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self._create_session()

    # ── UI construction ────────────────────────────────────

    def _build_ui(self):
        self._build_header()
        self._build_progress()
        self._build_panes()
        self._build_controls()
        self._build_status()

    def _build_header(self):
        header = tk.Frame(self, bg=THEME["bg2"])
        header.pack(fill="x")

        tk.Label(
            header,
            text="DISMANTLER  //  AI Plan Refinement",
            bg=THEME["bg2"],
            fg=THEME["accent"],
            font=THEME["font_interface_bold"],
            padx=8,
        ).pack(side="left", pady=6)

        # Passes spinbox (right side)
        passes_frame = tk.Frame(header, bg=THEME["bg2"])
        passes_frame.pack(side="right", padx=8, pady=4)

        tk.Label(
            passes_frame,
            text="Passes:",
            bg=THEME["bg2"],
            fg=THEME["fg"],
            font=THEME["font_interface_small"],
        ).pack(side="left", padx=(0, 4))

        self.passes_var = tk.StringVar(value="5")
        self.passes_spin = tk.Spinbox(
            passes_frame,
            from_=1,
            to=20,
            textvariable=self.passes_var,
            width=4,
            bg=THEME["bg3"],
            fg=THEME["fg"],
            font=THEME["font_interface_small"],
            buttonbackground=THEME["bg2"],
            relief="flat",
        )
        self.passes_spin.pack(side="left")

        # Model selector
        self.model_selector = ModelSelector(header)
        self.model_selector.pack(side="right", padx=4, pady=4)

    def _build_progress(self):
        """Row of pass indicator labels."""
        self.progress_frame = tk.Frame(self, bg=THEME["bg"])
        self.progress_frame.pack(fill="x", padx=10, pady=(6, 2))

        tk.Label(
            self.progress_frame,
            text="PASS:",
            bg=THEME["bg"],
            fg=THEME["fg_dim"],
            font=THEME["font_interface_bold"],
        ).pack(side="left", padx=(0, 6))

        self.pass_indicators = []
        self._rebuild_indicators()

    def _rebuild_indicators(self):
        """Rebuild the pass indicator labels based on current max_passes."""
        for lbl in self.pass_indicators:
            lbl.destroy()
        self.pass_indicators.clear()

        max_passes = self._get_max_passes()
        for i in range(max_passes):
            lbl = tk.Label(
                self.progress_frame,
                text=f" {i + 1} ",
                bg=THEME["bg3"],
                fg=THEME["fg_dim"],
                font=THEME["font_interface_bold"],
                relief="flat",
                padx=6,
                pady=2,
            )
            lbl.pack(side="left", padx=2)
            self.pass_indicators.append(lbl)

    def _build_panes(self):
        """Side-by-side: current plan (left) and AI output (right)."""
        paned = tk.PanedWindow(
            self,
            orient="horizontal",
            bg=THEME["bg"],
            sashwidth=4,
            sashrelief="flat",
        )
        paned.pack(fill="both", expand=True, padx=10, pady=(4, 0))

        # Left: Current Plan
        left = tk.Frame(paned, bg=THEME["bg2"])
        tk.Label(
            left,
            text="CURRENT PLAN",
            bg=THEME["bg2"],
            fg=THEME["fg_dim"],
            font=THEME["font_interface_small"],
            anchor="w",
        ).pack(fill="x", padx=6, pady=(6, 0))

        self.plan_text = scrolledtext.ScrolledText(
            left,
            bg=THEME["bg3"],
            fg=THEME["fg"],
            font=THEME["font_code_small"],
            state="disabled",
            relief="flat",
            wrap="none",
            padx=6,
            pady=4,
        )
        self.plan_text.pack(fill="both", expand=True, padx=6, pady=6)
        paned.add(left, stretch="always")

        # Right: AI Streaming Output
        right = tk.Frame(paned, bg=THEME["bg2"])
        tk.Label(
            right,
            text="AI OUTPUT",
            bg=THEME["bg2"],
            fg=THEME["fg_dim"],
            font=THEME["font_interface_small"],
            anchor="w",
        ).pack(fill="x", padx=6, pady=(6, 0))

        self.output_text = scrolledtext.ScrolledText(
            right,
            bg=THEME["bg3"],
            fg=THEME["fg"],
            font=THEME["font_code_small"],
            state="disabled",
            relief="flat",
            wrap="none",
            padx=6,
            pady=4,
        )
        self.output_text.pack(fill="both", expand=True, padx=6, pady=6)
        paned.add(right, stretch="always")

        # Tag config for streaming display
        self.output_text.tag_config("streaming", foreground=THEME["accent"])
        self.output_text.tag_config("complete", foreground=THEME["success"])

    def _build_controls(self):
        """Bottom control bar with action buttons."""
        bar = tk.Frame(self, bg=THEME["bg"])
        bar.pack(fill="x", padx=10, pady=(6, 4))

        self.cancel_btn = ToolbarButton(
            bar, text="Cancel", command=self._cancel
        )
        self.cancel_btn.pack(side="right", padx=2)

        self.auto_btn = AccentButton(
            bar, text="Auto-Accept", command=self._toggle_auto_accept
        )
        self.auto_btn.pack(side="right", padx=2)

        self.retry_btn = ToolbarButton(
            bar, text="Retry", command=self._retry_pass
        )
        self.retry_btn.pack(side="right", padx=2)

        self.run_btn = AccentButton(
            bar, text="Run Pass", command=self._run_pass
        )
        self.run_btn.pack(side="right", padx=2)

        # Initially disable retry (nothing to retry yet)
        self.retry_btn.config(state="disabled")

    def _build_status(self):
        """Status bar at the bottom."""
        self.status_label = tk.Label(
            self,
            text="Session ready. Select a model and click 'Run Pass' to begin.",
            bg=THEME["bg2"],
            fg=THEME["fg_dim"],
            font=THEME["font_interface_small"],
            anchor="w",
            padx=8,
        )
        self.status_label.pack(fill="x", side="bottom")

    # ── session lifecycle ──────────────────────────────────

    def _create_session(self):
        """Create a backend refinement session with the initial plan."""
        # Populate plan display
        self._set_plan_text(self.initial_plan)
        self._set_status(
            "Select a model and click 'Run Pass' to begin refinement."
        )

    def _ensure_session(self):
        """
        Create the backend session on-demand (at first pass execution).
        This ensures the model selector has loaded before we read from it.
        Returns True if session is ready.
        """
        if self._session_id:
            return True

        model = self.model_selector.get_selected()
        if not model or model in ("Scanning...", "Connection Error",
                                   "Ollama Offline", "No models found"):
            self._set_status(
                "No model available. Wait for models to load or check Ollama.",
                error=True,
            )
            return False

        max_passes = self._get_max_passes()

        result = self.backend.execute_task({
            "system": "transformer",
            "action": "refine_create",
            "file": self.file_path,
            "plan": self.initial_plan,
            "model": model,
            "max_passes": max_passes,
        })

        if result.get("status") == "ok":
            self._session_id = result["session_id"]
            self._rebuild_indicators()
            self._set_status(f"Session created ({max_passes} passes, model={model}).")
            return True
        else:
            self._set_status(f"Error: {result.get('message')}", error=True)
            return False

    # ── pass execution ─────────────────────────────────────

    def _run_pass(self):
        """Kick off the next refinement pass in a background thread."""
        if self._running:
            return
        if not self._ensure_session():
            return

        max_passes = self._get_max_passes()
        if self._current_pass >= max_passes:
            self._set_status("All passes complete.")
            return

        self._running = True
        self._disable_controls()
        self._clear_output()
        self._update_indicator(self._current_pass + 1, "current")
        self._set_status(f"Running pass {self._current_pass + 1}/{max_passes}...")

        threading.Thread(target=self._run_pass_bg, daemon=True).start()

    def _run_pass_bg(self):
        """Background thread: execute one refinement pass with streaming."""
        def on_token(token):
            self.after(0, lambda t=token: self._append_output(t))

        try:
            result = self.backend.execute_task({
                "system": "transformer",
                "action": "refine_pass",
                "session_id": self._session_id,
                "stream_callback": on_token,
            })

            if result.get("status") == "ok":
                pass_result = result["pass_result"]
                self.after(0, lambda: self._on_pass_complete(pass_result))
            else:
                msg = result.get("message", "Unknown error")
                self.after(0, lambda: self._on_pass_error(msg))
        except Exception as e:
            self.after(0, lambda: self._on_pass_error(str(e)))

    def _on_pass_complete(self, pass_result):
        """Handle a completed pass — update UI, optionally auto-advance."""
        self._running = False
        self._current_pass = pass_result["pass_number"]
        max_passes = self._get_max_passes()

        # Update plan display with the refined output
        self._set_plan_text(pass_result["output_plan"])

        # Mark this pass as approved in the progress bar
        self._update_indicator(self._current_pass, "success")

        if self._current_pass >= max_passes:
            self._set_status(
                f"All {max_passes} passes complete. Final plan ready."
            )
            self._enable_controls(final=True)
        elif self._auto_accept:
            self._set_status(
                f"Pass {self._current_pass}/{max_passes} auto-accepted. "
                f"Running next..."
            )
            self._enable_controls()
            self.after(500, self._run_pass)
        else:
            self._set_status(
                f"Pass {self._current_pass}/{max_passes} complete. "
                f"Approve to continue, Retry to re-run, or Auto-Accept remaining."
            )
            self._enable_controls()

    def _on_pass_error(self, message):
        """Handle a failed pass."""
        self._running = False
        self._update_indicator(self._current_pass + 1, "error")
        self._set_status(f"Error: {message}", error=True)
        self._enable_controls()

    # ── retry ──────────────────────────────────────────────

    def _retry_pass(self):
        """Re-run the most recent pass."""
        if self._running:
            return
        if not self._session_id:
            return
        if self._current_pass < 1:
            return

        self._running = True
        self._disable_controls()
        self._clear_output()
        self._update_indicator(self._current_pass, "warning")
        self._set_status(f"Retrying pass {self._current_pass}...")

        threading.Thread(target=self._retry_bg, daemon=True).start()

    def _retry_bg(self):
        """Background thread: retry the current pass."""
        def on_token(token):
            self.after(0, lambda t=token: self._append_output(t))

        try:
            result = self.backend.execute_task({
                "system": "transformer",
                "action": "refine_retry",
                "session_id": self._session_id,
                "stream_callback": on_token,
            })

            if result.get("status") == "ok":
                pass_result = result["pass_result"]
                self.after(0, lambda: self._on_pass_complete(pass_result))
            else:
                msg = result.get("message", "Unknown error")
                self.after(0, lambda: self._on_pass_error(msg))
        except Exception as e:
            self.after(0, lambda: self._on_pass_error(str(e)))

    # ── auto-accept toggle ─────────────────────────────────

    def _toggle_auto_accept(self):
        """Toggle auto-accept mode on/off."""
        self._auto_accept = not self._auto_accept

        if self._auto_accept:
            self.auto_btn.config(text="Stop Auto")
            self._set_status("Auto-accept ON. Passes will run automatically.")
            # If we're paused and have passes remaining, start the next one
            if not self._running and self._current_pass < self._get_max_passes():
                self._run_pass()
        else:
            self.auto_btn.config(text="Auto-Accept")
            self._set_status("Auto-accept OFF. Waiting for manual approval.")

    # ── cancel ─────────────────────────────────────────────

    def _cancel(self):
        """Cancel the current refinement session."""
        self._auto_accept = False
        self.auto_btn.config(text="Auto-Accept")

        if self._session_id:
            self.backend.execute_task({
                "system": "transformer",
                "action": "refine_cancel",
                "session_id": self._session_id,
            })

        self._set_status("Session cancelled.")
        self._enable_controls(final=True)

    # ── UI helpers ─────────────────────────────────────────

    def _set_plan_text(self, text):
        """Replace the content of the current plan pane."""
        self.plan_text.config(state="normal")
        self.plan_text.delete("1.0", "end")
        self.plan_text.insert("1.0", text)
        self.plan_text.config(state="disabled")

    def _append_output(self, token):
        """Append a streaming token to the AI output pane."""
        self.output_text.config(state="normal")
        self.output_text.insert("end", token, "streaming")
        self.output_text.see("end")
        self.output_text.config(state="disabled")

    def _clear_output(self):
        """Clear the AI output pane."""
        self.output_text.config(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.config(state="disabled")

    def _update_indicator(self, pass_number, state):
        """Update a pass indicator's color."""
        colors = {
            "pending":  THEME["bg3"],
            "current":  THEME["accent"],
            "success":  THEME["success"],
            "warning":  THEME["warning"],
            "error":    THEME["error"],
        }
        fg_colors = {
            "pending":  THEME["fg_dim"],
            "current":  "#ffffff",
            "success":  "#1e1e2e",
            "warning":  "#1e1e2e",
            "error":    "#ffffff",
        }
        idx = pass_number - 1
        if 0 <= idx < len(self.pass_indicators):
            self.pass_indicators[idx].config(
                bg=colors.get(state, THEME["bg3"]),
                fg=fg_colors.get(state, THEME["fg_dim"]),
            )

    def _set_status(self, text, error=False):
        """Update the status bar."""
        fg = THEME["error"] if error else THEME["fg_dim"]
        self.status_label.config(text=text, fg=fg)

    def _disable_controls(self):
        """Disable action buttons while a pass is running."""
        for btn in (self.run_btn, self.retry_btn, self.cancel_btn):
            btn.config(state="disabled")

    def _enable_controls(self, final=False):
        """Re-enable action buttons after a pass completes."""
        self.run_btn.config(state="disabled" if final else "normal")
        self.retry_btn.config(
            state="normal" if self._current_pass > 0 and not final else "disabled"
        )
        self.cancel_btn.config(state="normal")

    def _get_max_passes(self):
        """Read the max passes value from the spinbox."""
        try:
            return max(1, int(self.passes_var.get()))
        except (ValueError, tk.TclError):
            return 5

    def _on_close(self):
        """Clean up session when window is closed."""
        self._auto_accept = False
        if self._session_id:
            self.backend.execute_task({
                "system": "transformer",
                "action": "refine_cancel",
                "session_id": self._session_id,
            })
        self.destroy()
