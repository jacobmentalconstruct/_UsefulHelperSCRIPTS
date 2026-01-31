import tkinter as tk
from tkinter import ttk
from tkinter import scrolledtext
import logging
import threading
import traceback
import queue
from collections import deque
from typing import Optional


class _TkQueuedHandler(logging.Handler):
    """A logging handler that enqueues formatted log lines for the UI to drain in batches."""

    def __init__(self):
        super().__init__()
        self.q: "queue.Queue[str]" = queue.Queue()
        self._enabled = True

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)

    def emit(self, record: logging.LogRecord) -> None:
        # If the log window is closed/withdrawn, do not churn the queue.
        if not getattr(self, "_enabled", True):
            return

        try:
            msg = self.format(record)
        except Exception:
            msg = record.getMessage()
        try:
            self.q.put_nowait(msg)
        except Exception:
            pass


class LangBotUI:
    """
    UI Notes:
    - Tkinter runs all callbacks on the main thread (UI thread).
    - Any long-running work (LLM inference, network calls, embeddings, etc.) MUST
      run in a background thread, then use `after()` to update the UI safely.
    - We keep the Log Window attached to the root logger so the terminal can be
      hidden later.
    """

    def __init__(self, shell, backend):
        self.shell = shell
        self.backend = backend
        self.main_frame = shell.get_main_container()  # [cite: 124]

        # Log window state (closed by default)
        self._log_window: Optional[tk.Toplevel] = None
        self._log_text: Optional[tk.Text] = None
        self._tk_log_handler: Optional[_TkQueuedHandler] = None

        # Batched log rendering
        self._log_buffer = deque(maxlen=5000)  # ring buffer while window hidden
        self._log_draining = False

        # Chat send state
        self._pending = False
        self._thinking_index: Optional[str] = None

        self._build_ui()

        # Reduce ultra-noisy transport logs unless you want them
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)

    def _build_ui(self):
        # Header row
        header = ttk.Frame(self.main_frame)
        header.pack(fill="x", pady=(5, 0))

        # --- Live status chips (left of model picker) ---
        self._status_conn = tk.StringVar(value="Ollama: ?")
        self._status_loaded = tk.StringVar(value="Loaded: -")
        self._status_cpu = tk.StringVar(value="CPU/RAM: -")
        self._status_gpu = tk.StringVar(value="GPU/VRAM: -")

        status_frame = ttk.Frame(header)
        status_frame.pack(side="left", padx=(0, 12))

        ttk.Label(status_frame, textvariable=self._status_conn).pack(side="left", padx=(0, 10))
        ttk.Label(status_frame, textvariable=self._status_loaded).pack(side="left", padx=(0, 10))
        ttk.Label(status_frame, textvariable=self._status_cpu).pack(side="left", padx=(0, 10))
        ttk.Label(status_frame, textvariable=self._status_gpu).pack(side="left", padx=(0, 10))

        # Model Picker [cite: 101]
        models = self.backend.neural.get_available_models()
        self.model_var = tk.StringVar(value="qwen2.5-coder:7b")

        ttk.Label(header, text="Select Ollama Model:").pack(side="left", padx=(0, 8))
        self.picker = ttk.Combobox(header, textvariable=self.model_var, values=models, width=30)
        self.picker.pack(side="left")

        ttk.Button(header, text="Open Log Window", command=self._ensure_log_window).pack(side="right")

        # Start polling after UI exists
        self._start_status_poll()

        # Output
        self.display = tk.Text(self.main_frame, height=25, bg="#13131f", fg="#ccc", font=("Consolas", 10))
        self.display.pack(fill="both", expand=True, padx=10, pady=10)

        # Input
        self.input_field = tk.Entry(self.main_frame, bg="#1a1a25", fg="white", insertbackground="white")
        self.input_field.pack(fill="x", padx=10, pady=5)
        self.input_field.bind("<Return>", self._handle_send)

    def _start_status_poll(self):
        # Poll in background so UI never blocks
        self._status_polling = True
        self._status_inflight = False

        def _tick():
            if not getattr(self, "_status_polling", False):
                return

            # Prevent overlapping polls if one runs long.
            if not getattr(self, "_status_inflight", False):
                self._status_inflight = True
                threading.Thread(target=self._poll_status_worker, daemon=True).start()

            # Slightly slower poll to reduce churn.
            try:
                self.main_frame.after(2500, _tick)
            except Exception:
                pass

        _tick()

    def _poll_status_worker(self):
        try:
            data = None
            # Preferred consolidated endpoint
            if hasattr(self.backend.neural, "get_ui_status"):
                data = self.backend.neural.get_ui_status()

            # Fallback (older service): basic reachability + selected model
            if not data:
                alive = False
                try:
                    alive = bool(self.backend.neural.check_connection())
                except Exception:
                    alive = False
                data = {
                    "ok": alive,
                    "loaded_model": "",
                    "cpu_name": "",
                    "ram_used_gb": 0.0,
                    "ram_total_gb": 0.0,
                    "gpu_name": "",
                    "vram_used_gb": 0.0,
                    "vram_total_gb": 0.0,
                    "error": "",
                }

            self.main_frame.after(0, lambda: self._apply_status(data))
        except Exception:
            # Never crash UI from status thread
            pass
        finally:
            # Always release inflight guard
            try:
                self._status_inflight = False
            except Exception:
                pass

    def _apply_status(self, st: dict):
        ok = bool(st.get("ok"))
        err = (st.get("error") or "").strip()
        loaded = (st.get("loaded_model") or "").strip()

        cpu_name = (st.get("cpu_name") or "").strip()
        ram_used = float(st.get("ram_used_gb") or 0.0)
        ram_total = float(st.get("ram_total_gb") or 0.0)

        gpu_name = (st.get("gpu_name") or "").strip()
        vram_used = float(st.get("vram_used_gb") or 0.0)
        vram_total = float(st.get("vram_total_gb") or 0.0)

        self._status_conn.set(f"Ollama: {'OK' if ok else 'OFF'}" + (f" ({err})" if (not ok and err) else ""))
        self._status_loaded.set(f"Loaded: {loaded if loaded else '-'}")

        # Compact formatting; show totals only if we have them
        if ram_total > 0:
            base_cpu = cpu_name if cpu_name else "CPU"
            self._status_cpu.set(f"{base_cpu} | RAM {ram_used:.2f}/{ram_total:.2f} GB")
        else:
            self._status_cpu.set(f"{cpu_name if cpu_name else 'CPU'} | RAM -")

        if vram_total > 0:
            base_gpu = gpu_name if gpu_name else "GPU"
            self._status_gpu.set(f"{base_gpu} | VRAM {vram_used:.2f}/{vram_total:.2f} GB")
        else:
            # If we have a GPU name but no VRAM, still show it
            if gpu_name:
                self._status_gpu.set(f"{gpu_name} | VRAM -")
            else:
                self._status_gpu.set("GPU/VRAM: -")

    def _start_log_drain(self):
        """Drain queued log messages in batches to avoid UI stutter."""
        if self._log_draining:
            return
        self._log_draining = True

        def _tick():
            if not self._log_draining:
                return

            # Pull from queue into ring buffer and/or UI
            try:
                if self._tk_log_handler is not None:
                    n = 0
                    while n < 300:
                        try:
                            line = self._tk_log_handler.q.get_nowait()
                        except Exception:
                            break
                        self._log_buffer.append(line)
                        n += 1
            except Exception:
                pass

            # If window is visible, flush recent buffer to widget
            try:
                if (
                    self._log_window is not None
                    and self._log_text is not None
                    and self._log_window.winfo_exists()
                    and self._log_window.state() != "withdrawn"
                ):
                    self._flush_log_buffer()
            except Exception:
                pass

            try:
                self.main_frame.after(100, _tick)  # 10Hz drain
            except Exception:
                pass

        _tick()

    def _flush_log_buffer(self):
        """Flush the current ring buffer into the log widget (best-effort)."""
        if self._log_text is None:
            return
        try:
            # Repaint the last N lines for speed
            self._log_text.delete("1.0", tk.END)
            for line in list(self._log_buffer)[-2000:]:
                self._log_text.insert(tk.END, line + "\n")
            self._log_text.see(tk.END)
        except Exception:
            pass

    def _ensure_log_window(self):
        """Create/show the log window and hook root logging into it."""
        if self._log_window is not None and self._log_window.winfo_exists():
            # Just show it (avoid repeated focus stealing / flashing)
            try:
                if self._tk_log_handler is not None:
                    self._tk_log_handler.set_enabled(True)
            except Exception:
                pass
            try:
                self._log_window.deiconify()
            except Exception:
                pass
            return

        self._log_window = tk.Toplevel(self.main_frame)
        self._log_window.title("LangBOT - Live Log")
        self._log_window.geometry("900x350")

        self._log_text = scrolledtext.ScrolledText(
            self._log_window,
            height=20,
            bg="#0f0f18",
            fg="#cfcfe6",
            insertbackground="#cfcfe6",
            font=("Consolas", 9),
        )
        self._log_text.pack(fill="both", expand=True, padx=8, pady=8)

        # Hide (withdraw) on close so it stays available without destroying handlers
        def _on_close():
            try:
                if self._tk_log_handler is not None:
                    self._tk_log_handler.set_enabled(False)
                self._log_window.withdraw()
            except Exception:
                pass

        self._log_window.protocol("WM_DELETE_WINDOW", _on_close)

        # Install queued handler exactly once
        if self._tk_log_handler is None:
            self._tk_log_handler = _TkQueuedHandler()
            self._tk_log_handler.setLevel(logging.INFO)
            self._tk_log_handler.setFormatter(
                logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
            )

            root_logger = logging.getLogger()
            root_logger.setLevel(logging.INFO)
            root_logger.addHandler(self._tk_log_handler)

            # Start batched draining (safe to run even if window is later hidden)
            self._start_log_drain()

            logging.getLogger("UI").info("Queued log handler attached (batched drain enabled).")

        # Immediately flush whatever we buffered so far
        try:
            self._flush_log_buffer()
        except Exception:
            pass

    # ---------------------------
    # Chat / Inference
    # ---------------------------

    def _handle_send(self, event):
        """Kick off inference in a background thread so the UI stays responsive."""
        if self._pending:
            # Optional: ignore input while a request is running
            return

        query = self.input_field.get().strip()
        if not query:
            return

        self._pending = True

        # Append user message
        self.display.insert(tk.END, f"\nYOU: {query}\n")
        self.display.see(tk.END)
        self.input_field.delete(0, tk.END)

        # Disable input while running
        self.input_field.config(state="disabled")

        # Insert a placeholder "thinking..." line we can later replace
        self.display.insert(tk.END, "BOT: (thinking...)\n")
        self.display.see(tk.END)

        # Save index of the placeholder line start so we can replace it later
        # "end-1l" refers to the start of the last line inserted
        self._thinking_index = self.display.index("end-1l")

        # Snapshot current model selection for this request
        smart_model = self.model_var.get()

        # Run the backend work off the UI thread
        thread = threading.Thread(
            target=self._inference_worker,
            args=(query, smart_model),
            daemon=True
        )
        thread.start()

    def _inference_worker(self, query: str, smart_model: str):
        logger = logging.getLogger("UI")
        try:
            # Update backend model preference before invoking
            # (This call should be quick; inference is the long part.)
            self.backend.neural.update_models(
                fast_model="qwen2.5-coder:1.5b",
                smart_model=smart_model,
                embed_model="mxbai-embed-large",
            )

            res = self.backend.workflow.invoke({"question": query})
            answer = (res.get("answer", "") or "").strip()
            if not answer:
                answer = "[No answer returned]"

            logger.info("Inference complete.")
        except Exception:
            logger.error("Inference failed:\n" + traceback.format_exc())
            answer = "[ERROR] Inference failed (see log window)."

        # UI updates must happen on Tk thread
        self.main_frame.after(0, lambda: self._finish_inference(answer))

    def _finish_inference(self, answer: str):
        """Replace the placeholder line, re-enable input, clear pending flag."""
        try:
            # Remove placeholder "BOT: (thinking...)" line
            if self._thinking_index:
                self.display.delete(self._thinking_index, self._thinking_index + " lineend+1c")
        except Exception:
            # If index math is off, just append the answer
            pass

        self.display.insert(tk.END, f"BOT: {answer}\n")
        self.display.see(tk.END)

        self._pending = False
        self._thinking_index = None
        self.input_field.config(state="normal")
        self.input_field.focus_set()


