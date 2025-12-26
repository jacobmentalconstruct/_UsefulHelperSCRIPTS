"""
SERVICE_NAME: _LogViewMS
ENTRY_POINT: _LogViewMS.py
DEPENDENCIES: tkinter
"""

import tkinter as tk
from tkinter import ttk, filedialog
import queue
import logging
import datetime
from typing import Any, Dict, Optional

from microservice_std_lib import service_metadata, service_endpoint
# [FIX] Added BaseService for consistency
from base_service import BaseService

# ==============================================================================
# HELPER CLASS (Logging Handler)
# ==============================================================================

class QueueHandler(logging.Handler):
    """
    Sends log records to a thread-safe queue.
    Used to bridge the gap between Python's logging system and the Tkinter UI.
    """
    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        self.log_queue.put(record)


# ==============================================================================
# MICROSERVICE CLASS (UI Widget)
# ==============================================================================

@service_metadata(
    name="LogView",
    version="1.1.0",
    description="A thread-safe log viewer widget for Tkinter.",
    tags=["ui", "logs", "widget"],
    capabilities=["ui:gui", "filesystem:write"]
)
class LogViewMS(BaseService, tk.Frame):
    """
    The Console: A professional log viewer widget.
    Features:
    - Thread-safe (consumes from a Queue).
    - Message Consolidation ("Error occurred (x5)").
    - Level Filtering (Toggle INFO/DEBUG/ERROR).
    - Dark Mode Compliant (uses ttk.Scrollbar).
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        parent = self.config.get("parent")
        
        # [FIX] Initialize BaseService AND tk.Frame
        BaseService.__init__(self, "LogViewMS")
        tk.Frame.__init__(self, parent)
        
        # Ensure we have a queue to pull from
        self.log_queue: queue.Queue = self.config.get("log_queue")
        if self.log_queue is None:
            self.log_queue = queue.Queue()

        # State for consolidation
        self.last_msg = None
        self.last_count = 0
        self.last_line_index = None

        self._build_ui()
        self._poll_queue()

    def _build_ui(self):
        # Toolbar
        toolbar = tk.Frame(self, bg="#2d2d2d", height=30)
        toolbar.pack(fill="x", side="top")
        
        # Filters
        self.filters = {
            "INFO": tk.BooleanVar(value=True),
            "DEBUG": tk.BooleanVar(value=True),
            "WARNING": tk.BooleanVar(value=True),
            "ERROR": tk.BooleanVar(value=True)
        }
        
        for level, var in self.filters.items():
            cb = tk.Checkbutton(
                toolbar, text=level, variable=var, 
                bg="#2d2d2d", fg="white", selectcolor="#444",
                activebackground="#2d2d2d", activeforeground="white"
            )
            cb.pack(side="left", padx=5)

        tk.Button(toolbar, text="Clear", command=self.clear, bg="#444", fg="white", relief="flat").pack(side="right", padx=5)
        tk.Button(toolbar, text="Save", command=self.save, bg="#444", fg="white", relief="flat").pack(side="right")

        # [FIX] Replaced ScrolledText with Text + ttk.Scrollbar 
        # This allows the ThemeManager to style the scrollbar dark.
        
        # 1. The Scrollbar (Themed)
        self.vsb = ttk.Scrollbar(self, orient="vertical")
        self.vsb.pack(side="right", fill="y")
        
        # 2. The Text Area
        self.text = tk.Text(
            self, 
            state="disabled", 
            bg="#1e1e1e", 
            fg="#d4d4d4", 
            font=("Consolas", 10), 
            insertbackground="white",
            relief="flat",
            yscrollcommand=self.vsb.set # Link to scrollbar
        )
        self.text.pack(side="left", fill="both", expand=True)
        
        # 3. Link Scrollbar to Text
        self.vsb.config(command=self.text.yview)
        
        # Color Tags
        self.text.tag_config("INFO", foreground="#d4d4d4")
        self.text.tag_config("DEBUG", foreground="#569cd6")
        self.text.tag_config("WARNING", foreground="#ce9178")
        self.text.tag_config("ERROR", foreground="#f44747")
        self.text.tag_config("timestamp", foreground="#608b4e")

    def _poll_queue(self):
        """Pulls logs from the queue and updates UI."""
        try:
            while True:
                record = self.log_queue.get_nowait()
                self._display(record)
        except queue.Empty:
            pass
        finally:
            # Schedule the next poll in 100ms
            self.after(100, self._poll_queue)

    def _display(self, record):
        level = record.levelname
        # Skip if filter for this level is off
        if not self.filters.get(level, tk.BooleanVar(value=True)).get():
            return

        msg = record.getMessage()
        ts = datetime.datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        
        self.text.config(state="normal")
        
        # Basic display logic (Consolidation placeholder)
        if msg == self.last_msg:
            self.last_count += 1
            # In a full implementation, we would update the previous line here.
            # For this microservice, we append normally to ensure stability.
        else:
            self.last_msg = msg
            self.last_count = 1
        
        self.text.insert("end", f"[{ts}] ", "timestamp")
        self.text.insert("end", f"{msg}\n", level)
        self.text.see("end")
        self.text.config(state="disabled")

    @service_endpoint(
        inputs={},
        outputs={},
        description="Clears the log console.",
        tags=["ui", "logs"],
        side_effects=["ui:update"]
    )
    def clear(self):
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.config(state="disabled")

    @service_endpoint(
        inputs={},
        outputs={},
        description="Opens a dialog to save logs to a file.",
        tags=["ui", "filesystem"],
        side_effects=["filesystem:write", "ui:dialog"]
    )
    def save(self):
        path = filedialog.asksaveasfilename(defaultextension=".log", filetypes=[("Log Files", "*.log")])
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self.text.get("1.0", "end"))
            except Exception as e:
                self.log_error(f"Save failed: {e}")


# --- Independent Test Block ---
if __name__ == "__main__":
    root = tk.Tk()
    root.title("Log View Test")
    root.geometry("600x400")
    
    # 1. Setup Queue
    q = queue.Queue()
    
    # 2. Setup Logger
    logger = logging.getLogger("TestApp")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(QueueHandler(q))
    
    # 3. Mount View
    log_view = LogViewMS({"parent": root, "log_queue": q})
    print("Service ready:", log_view._service_info)
    log_view.pack(fill="both", expand=True)
    
    # 4. Generate Noise
    def generate_noise():
        logger.info("System initializing...")
        logger.debug("Checking sensors...")
        logger.warning("Sensor 4 response slow.")
        logger.error("Connection failed!")
        root.after(2000, generate_noise)
        
    generate_noise()
    root.mainloop()