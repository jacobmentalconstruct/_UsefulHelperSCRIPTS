# _training/trainer_ui.py
# Mind-Shard Trainer — Tkinter shell for the QLoRA training pipeline.
#
# Run from the project root with the INFERENCE conda env (no training deps needed here):
#   python _training/trainer_ui.py
#
# The app launches prepare_dataset.py and train.py as subprocesses using
# whichever Python executable you point it at (your lora_train env).

from tkinter import (
    Tk, Text, Button, Entry, Frame, Label, Scrollbar, OptionMenu, Spinbox,
    StringVar, IntVar, BooleanVar, Checkbutton, filedialog, END,
    LEFT, RIGHT, TOP, X, BOTH, Y, W
)
from tkinter.font import Font
from tkinter import messagebox
from pathlib import Path
import subprocess
import threading
import sys
import os

# ─── PATHS ─────────────────────────────────────────────────────────────────────
TRAINING_DIR = Path(__file__).resolve().parent
ROOT_DIR     = TRAINING_DIR.parent
PREPARE_SCRIPT = TRAINING_DIR / "prepare_dataset.py"
TRAIN_SCRIPT   = TRAINING_DIR / "train.py"

# ─── APPEARANCE ────────────────────────────────────────────────────────────────
BG         = "#2E2E2E"
BG_LIGHT   = "#3A3A3A"
BG_INPUT   = "#404040"
FG         = "#D3D3D3"
FG_DIM     = "#888888"
FG_GREEN   = "#7EC8A4"
FG_YELLOW  = "#E5C07B"
FG_RED     = "#E06C75"
ACCENT     = "#61AFEF"
FONT_FACE  = "Consolas"
FONT_SIZE  = 10

WINDOW_W   = 760
WINDOW_H   = 620

# ─── GLOBAL STATE ──────────────────────────────────────────────────────────────
current_process = None   # the running subprocess, if any


# ─── HELPERS ───────────────────────────────────────────────────────────────────

def display(text, color=None):
    """Thread-safe append to the output box."""
    def _insert():
        output_box.config(state="normal")
        tag = color or "normal"
        output_box.insert(END, text + "\n", tag)
        output_box.config(state="disabled")
        output_box.see(END)
    root.after(0, _insert)


def stream_process(proc):
    """
    Read stdout of a subprocess line-by-line in a background thread,
    forwarding each line to display().  Signals completion when done.
    """
    for raw in iter(proc.stdout.readline, ""):
        line = raw.rstrip()
        # Colour-code key lines for readability
        if any(k in line for k in ("✅", "Training complete", "GGUF saved")):
            display(line, "green")
        elif any(k in line for k in ("⚠️", "Warning", "warn")):
            display(line, "yellow")
        elif any(k in line for k in ("❌", "Error", "error", "Traceback", "OOM")):
            display(line, "red")
        elif line.startswith("{'loss'") or "loss" in line.lower() and "step" in line.lower():
            display(line, "accent")
        else:
            display(line)

    proc.stdout.close()
    rc = proc.wait()

    if rc == 0:
        display("\n── Process finished successfully. ──", "green")
    elif rc == -1 or rc is None:
        display("\n── Process stopped. ──", "yellow")
    else:
        display(f"\n── Process exited with code {rc}. ──", "red")

    root.after(0, _on_process_done)


def _on_process_done():
    """Re-enable buttons after a subprocess finishes."""
    global current_process
    current_process = None
    _set_buttons_running(False)


def _set_buttons_running(running: bool):
    state_run  = "disabled" if running else "normal"
    state_stop = "normal"   if running else "disabled"
    btn_prepare.config(state=state_run)
    btn_smoke.config(state=state_run)
    btn_train.config(state=state_run)
    btn_stop.config(state=state_stop)


def _get_python():
    py = python_path_var.get().strip()
    if not py:
        messagebox.showerror("No Python", "Browse to the lora_train env's python.exe first.")
        return None
    if not Path(py).exists():
        messagebox.showerror("Not found", f"Python not found:\n{py}")
        return None
    return py


def _launch(script: Path, extra_args: list[str]):
    """Launch a script as a subprocess and start streaming its output."""
    global current_process

    py = _get_python()
    if py is None:
        return

    cmd = [py, str(script)] + extra_args
    display(f"\n▶ {' '.join(cmd)}\n", "accent")

    try:
        current_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            cwd=str(ROOT_DIR),
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
    except Exception as e:
        display(f"❌ Failed to start process: {e}", "red")
        return

    _set_buttons_running(True)
    threading.Thread(target=stream_process, args=(current_process,), daemon=True).start()


# ─── BUTTON COMMANDS ───────────────────────────────────────────────────────────

def browse_python():
    path = filedialog.askopenfilename(
        title="Select python.exe for lora_train env",
        filetypes=[("Python executable", "python.exe python"), ("All files", "*.*")],
    )
    if path:
        python_path_var.set(path)


def cmd_prepare():
    _launch(PREPARE_SCRIPT, [])


def cmd_smoke():
    _launch(TRAIN_SCRIPT, _build_train_args() + ["--smoke-test"])


def cmd_train():
    if not messagebox.askyesno(
        "Start full training?",
        "This may take hours depending on your dataset size.\n\nContinue?"
    ):
        return
    _launch(TRAIN_SCRIPT, _build_train_args())


def cmd_stop():
    global current_process
    if current_process and current_process.poll() is None:
        current_process.terminate()
        display("\n⏹ Stop requested…", "yellow")


def _build_train_args() -> list[str]:
    args = [
        "--model",   model_var.get(),
        "--epochs",  str(epochs_var.get()),
        "--seq-len", str(seqlen_var.get()),
        "--quant",   quant_var.get(),
        "--lora-r",  str(lora_r_var.get()),
    ]
    return args


# ─── UI SETUP ──────────────────────────────────────────────────────────────────

root = Tk()
root.title("Mind-Shard Trainer")
root.geometry(f"{WINDOW_W}x{WINDOW_H}")
root.configure(bg=BG)
root.resizable(True, True)

font       = Font(family=FONT_FACE, size=FONT_SIZE)
font_bold  = Font(family=FONT_FACE, size=FONT_SIZE, weight="bold")
font_small = Font(family=FONT_FACE, size=FONT_SIZE - 1)

# ── Row 1: Python path ──────────────────────────────────────────────────────────
python_path_var = StringVar(value="")

row_python = Frame(root, bg=BG)
row_python.pack(side=TOP, fill=X, padx=10, pady=(10, 2))

Label(row_python, text="Python:", bg=BG, fg=FG_DIM, font=font).pack(side=LEFT)
Entry(
    row_python, textvariable=python_path_var,
    font=font, bg=BG_INPUT, fg=FG, insertbackground="white", relief="flat"
).pack(side=LEFT, fill=X, expand=True, padx=(4, 4))
Button(
    row_python, text="Browse", font=font,
    bg=BG_LIGHT, fg=FG, relief="flat", command=browse_python
).pack(side=LEFT)

Label(
    root,
    text="  Point to your lora_train conda env's python.exe",
    bg=BG, fg=FG_DIM, font=font_small, anchor=W
).pack(side=TOP, fill=X, padx=14)

# ── Separator ───────────────────────────────────────────────────────────────────
Frame(root, bg=BG_LIGHT, height=1).pack(fill=X, padx=10, pady=6)

# ── Row 2: Config grid ──────────────────────────────────────────────────────────
MODELS = [
    "unsloth/mistral-7b-instruct-v0.3-bnb-4bit",
    "unsloth/phi-3-mini-4k-instruct-bnb-4bit",
    "unsloth/llama-3-8b-instruct-bnb-4bit",
]
QUANTS = ["q4_k_m", "q5_k_m", "q8_0"]

model_var  = StringVar(value=MODELS[0])
epochs_var = IntVar(value=3)
seqlen_var = IntVar(value=2048)
quant_var  = StringVar(value=QUANTS[0])
lora_r_var = IntVar(value=16)

cfg_frame = Frame(root, bg=BG)
cfg_frame.pack(side=TOP, fill=X, padx=10, pady=2)

# Helper: labelled widget pair
def cfg_label(parent, text, col):
    Label(parent, text=text, bg=BG, fg=FG_DIM, font=font).grid(
        row=0, column=col, sticky=W, padx=(0 if col == 0 else 12, 2), pady=2
    )

def cfg_entry_int(parent, var, col, width=6):
    Spinbox(
        parent, textvariable=var, from_=1, to=9999, width=width,
        font=font, bg=BG_INPUT, fg=FG, buttonbackground=BG_LIGHT,
        relief="flat", insertbackground="white"
    ).grid(row=0, column=col + 1, sticky=W, padx=(0, 4))

# Model (spans a wide dropdown on row 0)
Label(cfg_frame, text="Model:", bg=BG, fg=FG_DIM, font=font).grid(
    row=0, column=0, sticky=W, pady=2, padx=(0, 2))
model_menu = OptionMenu(cfg_frame, model_var, *MODELS)
model_menu.config(font=font, bg=BG_INPUT, fg=FG, relief="flat",
                  highlightthickness=0, activebackground=BG_LIGHT)
model_menu["menu"].config(font=font, bg=BG_INPUT, fg=FG)
model_menu.grid(row=0, column=1, columnspan=7, sticky=W, padx=(0, 10))

# Second row: Epochs / Seq Len / LoRA r / Quant
cfg_frame2 = Frame(root, bg=BG)
cfg_frame2.pack(side=TOP, fill=X, padx=10, pady=2)

def lbl(text): return Label(cfg_frame2, text=text, bg=BG, fg=FG_DIM, font=font)
def spn(var, lo=1, hi=9999, w=6):
    return Spinbox(cfg_frame2, textvariable=var, from_=lo, to=hi, width=w,
                   font=font, bg=BG_INPUT, fg=FG, buttonbackground=BG_LIGHT,
                   relief="flat", insertbackground="white")

lbl("Epochs:").pack(side=LEFT)
spn(epochs_var, 1, 20, 4).pack(side=LEFT, padx=(2, 14))

lbl("Seq Len:").pack(side=LEFT)
spn(seqlen_var, 256, 8192, 6).pack(side=LEFT, padx=(2, 14))

lbl("LoRA r:").pack(side=LEFT)
spn(lora_r_var, 4, 128, 4).pack(side=LEFT, padx=(2, 14))

lbl("Quant:").pack(side=LEFT)
quant_menu = OptionMenu(cfg_frame2, quant_var, *QUANTS)
quant_menu.config(font=font, bg=BG_INPUT, fg=FG, relief="flat",
                  highlightthickness=0, activebackground=BG_LIGHT)
quant_menu["menu"].config(font=font, bg=BG_INPUT, fg=FG)
quant_menu.pack(side=LEFT, padx=(2, 0))

# ── Separator ───────────────────────────────────────────────────────────────────
Frame(root, bg=BG_LIGHT, height=1).pack(fill=X, padx=10, pady=8)

# ── Row 3: Action buttons ────────────────────────────────────────────────────────
btn_frame = Frame(root, bg=BG)
btn_frame.pack(side=TOP, fill=X, padx=10, pady=(0, 6))

def make_btn(parent, text, cmd, fg_color=FG):
    return Button(
        parent, text=text, command=cmd,
        font=font_bold, bg=BG_LIGHT, fg=fg_color,
        relief="flat", padx=10, pady=4,
        activebackground=BG_INPUT, activeforeground=fg_color,
    )

btn_prepare = make_btn(btn_frame, "Prepare Dataset", cmd_prepare, FG_YELLOW)
btn_prepare.pack(side=LEFT, padx=(0, 6))

btn_smoke = make_btn(btn_frame, "▶ Smoke Test", cmd_smoke, ACCENT)
btn_smoke.pack(side=LEFT, padx=(0, 6))

btn_train = make_btn(btn_frame, "▶ Full Train", cmd_train, FG_GREEN)
btn_train.pack(side=LEFT, padx=(0, 6))

btn_stop = make_btn(btn_frame, "⏹ Stop", cmd_stop, FG_RED)
btn_stop.config(state="disabled")
btn_stop.pack(side=LEFT)

# ── Row 4: Output log ────────────────────────────────────────────────────────────
log_frame = Frame(root, bg=BG)
log_frame.pack(side=TOP, fill=BOTH, expand=True, padx=10, pady=(0, 10))

output_box = Text(
    log_frame, wrap="word", font=font, state="disabled",
    bg="#1E1E1E", fg=FG, insertbackground="white", relief="flat",
    selectbackground=BG_LIGHT,
)
output_box.pack(side=LEFT, fill=BOTH, expand=True)

log_scroll = Scrollbar(log_frame, command=output_box.yview, bg=BG_LIGHT)
log_scroll.pack(side=RIGHT, fill=Y)
output_box.config(yscrollcommand=log_scroll.set)

# Colour tags
output_box.tag_config("normal",  foreground=FG)
output_box.tag_config("green",   foreground=FG_GREEN)
output_box.tag_config("yellow",  foreground=FG_YELLOW)
output_box.tag_config("red",     foreground=FG_RED)
output_box.tag_config("accent",  foreground=ACCENT)

# ── Startup message ──────────────────────────────────────────────────────────────
display("Mind-Shard Trainer ready.", "green")
display("1. Browse to your lora_train conda env's python.exe")
display("2. Prepare Dataset → Smoke Test → Full Train\n")

root.mainloop()
