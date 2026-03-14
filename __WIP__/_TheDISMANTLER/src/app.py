"""
AppBootstrapper – The Process Guard.
Entry point that launches the environment, manages the system console,
and orchestrates the Backend Engine → UI Framework lifecycle.
"""
import sys
import os
import tkinter as tk
import threading

# Ensure bare imports resolve from src/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from theme import THEME
from backend.main import BackendEngine
from ui.main_window import MainWindow
import config


class AppBootstrapper(tk.Tk):
    """
    System Console Modal.
    A thread-safe logging sink that captures and displays real-time
    initialization and error logs. Launches the BackendEngine then
    the MainWindow once the backend is ready.
    """

    def __init__(self):
        super().__init__()
        self.title("DISMANTLER System Console")
        self.geometry("700x420")
        self.configure(bg=THEME["bg"])

        # Load saved preference (defaults to True if no prefs file yet)
        self.keep_open = tk.BooleanVar(value=config.get("show_console"))
        self.main_app = None

        self._build_console()

        # Trace fires on every future change to keep_open — from the checkbox
        # in this console OR from the Preferences dialog in MainWindow.
        # Important: trace is added AFTER the initial value is set above so it
        # does NOT fire at construction time.
        self.keep_open.trace_add("write", self._on_keep_open_changed)

        self.backend = BackendEngine(self.log)

        # Launch sequence in a daemon thread to keep the console responsive
        threading.Thread(target=self._launch_sequence, daemon=True).start()

    # ── console UI ──────────────────────────────────────────

    def _build_console(self):
        header = tk.Label(
            self,
            text="DISMANTLER  //  System Console",
            bg=THEME["bg"],
            fg=THEME["accent"],
            font=THEME["font_interface_bold"],
            anchor="w",
            padx=10,
        )
        header.pack(fill="x", pady=(8, 0))

        self.log_area = tk.Text(
            self,
            bg=THEME["bg3"],
            fg=THEME["fg"],
            font=THEME["font_code_small"],
            relief="flat",
            state="disabled",
            padx=8,
            pady=6,
        )
        self.log_area.pack(fill="both", expand=True, padx=10, pady=8)

        self.log_area.tag_config("thread", foreground=THEME["fg_dim"])
        self.log_area.tag_config("ok", foreground=THEME["success"])
        self.log_area.tag_config("err", foreground=THEME["error"])

        ctrl_frame = tk.Frame(self, bg=THEME["bg"])
        ctrl_frame.pack(fill="x", side="bottom", padx=10, pady=(0, 8))

        tk.Checkbutton(
            ctrl_frame,
            text="Show console on startup",
            variable=self.keep_open,
            bg=THEME["bg"],
            fg=THEME["fg"],
            selectcolor=THEME["bg2"],
            activebackground=THEME["bg"],
            activeforeground=THEME["fg"],
            font=THEME["font_interface_small"],
        ).pack(side="left")

    # ── thread-safe logging ─────────────────────────────────

    def log(self, message, tag=None):
        """
        Append a message to the console log area.
        Safe to call from any thread.
        """
        def _insert():
            self.log_area.config(state="normal")
            thread_name = threading.current_thread().name
            self.log_area.insert("end", f"[{thread_name}] ", "thread")
            self.log_area.insert("end", f"{message}\n", tag or "")
            self.log_area.see("end")
            self.log_area.config(state="disabled")

        if threading.current_thread() is threading.main_thread():
            _insert()
        else:
            self.after(0, _insert)

    # ── lifecycle ───────────────────────────────────────────

    def _launch_sequence(self):
        """Boot the backend, then open the main window on the UI thread."""
        self.log("Initializing Backend Engine...")
        try:
            self.backend.boot()
            self.log("Backend boot complete.", "ok")
        except Exception as e:
            self.log(f"BOOT FAILED: {e}", "err")
            return

        self.log("Launching User Interface Framework...")
        self.after(0, self._open_main_window)

    def _on_keep_open_changed(self, *_args):
        """
        Trace callback — fires whenever keep_open changes from any source
        (the checkbox in this console, the Preferences dialog, etc.).
        Immediately shows or hides the console and persists the preference.
        """
        show = self.keep_open.get()
        config.set_pref("show_console", show)
        # Only touch window visibility after the main app has launched;
        # before that, _open_main_window handles the initial hide.
        if self.main_app:
            if show:
                self.deiconify()
                self.lift()
            else:
                self.withdraw()

    def _open_main_window(self):
        self.main_app = MainWindow(self.backend, master=self)
        self.log("MainWindow launched.", "ok")

        if not self.keep_open.get():
            self.withdraw()


if __name__ == "__main__":
    app = AppBootstrapper()
    app.mainloop()
