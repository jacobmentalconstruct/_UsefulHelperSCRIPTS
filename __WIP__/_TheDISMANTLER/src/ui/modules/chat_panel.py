"""
Chat panel sidebar for workspace tabs.
Contains a message history display, model selector, and input area.
"""
import tkinter as tk
from theme import THEME
from ui.modules.model_selector import ModelSelector
from ui.modules._buttons import AccentButton


class ChatPanel(tk.Frame):
    """
    Sidebar chat interface with:
    - Ollama model selector at the top
    - Scrollable message history
    - Text input with Send button
    """

    def __init__(self, parent, on_send=None, **kwargs):
        super().__init__(parent, bg=THEME["bg2"], **kwargs)
        self._on_send = on_send
        self._selected_model = None

        # --- model selector ---
        self.model_selector = ModelSelector(
            self, on_change=self._model_changed
        )
        self.model_selector.pack(fill="x", padx=4, pady=(6, 4))

        # --- separator ---
        tk.Frame(self, bg=THEME["fg_dim"], height=1).pack(fill="x", padx=4, pady=2)

        # --- message history ---
        self.history = tk.Text(
            self,
            bg=THEME["bg3"],
            fg=THEME["fg"],
            font=THEME["font_code_small"],
            state="disabled",
            wrap="word",
            relief="flat",
            padx=6,
            pady=4,
        )
        self.history.pack(fill="both", expand=True, padx=4, pady=4)

        self.history.tag_config("user", foreground=THEME["accent"])
        self.history.tag_config("assistant", foreground=THEME["success"])
        self.history.tag_config("system", foreground=THEME["fg_dim"])

        # --- input area ---
        input_frame = tk.Frame(self, bg=THEME["bg2"])
        input_frame.pack(fill="x", padx=4, pady=(0, 6))

        self.input_box = tk.Text(
            input_frame,
            bg=THEME["bg3"],
            fg=THEME["fg"],
            insertbackground=THEME["accent"],
            font=THEME["font_interface"],
            height=3,
            wrap="word",
            relief="flat",
            padx=6,
            pady=4,
        )
        self.input_box.pack(fill="x", side="top", pady=(0, 4))
        self.input_box.bind("<Shift-Return>", lambda e: None)  # allow newline
        self.input_box.bind("<Return>", self._on_enter)

        self.send_btn = AccentButton(
            input_frame, text="Send", command=self._send_message
        )
        self.send_btn.pack(side="right")

    # ── public API ──────────────────────────────────────────

    def append_message(self, role, content):
        """Add a message to the history. role: 'user' | 'assistant' | 'system'."""
        self.history.config(state="normal")
        prefix = {"user": "You", "assistant": "AI", "system": "SYS"}.get(role, role)
        self.history.insert("end", f"[{prefix}] ", role)
        self.history.insert("end", f"{content}\n\n")
        self.history.see("end")
        self.history.config(state="disabled")

    def get_selected_model(self):
        return self._selected_model

    def clear_history(self):
        self.history.config(state="normal")
        self.history.delete("1.0", "end")
        self.history.config(state="disabled")

    # ── internal ────────────────────────────────────────────

    def _model_changed(self, model_name):
        self._selected_model = model_name

    def _on_enter(self, event):
        self._send_message()
        return "break"  # suppress default newline

    def _send_message(self):
        content = self.input_box.get("1.0", "end-1c").strip()
        if not content:
            return

        self.input_box.delete("1.0", "end")
        self.append_message("user", content)

        if self._on_send:
            self._on_send(content, self._selected_model)
