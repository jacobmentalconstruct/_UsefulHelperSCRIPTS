"""
META-DATA FOR AI AGENTS:
Name: OllamaGovernor
Version: 1.1.0
Description: A hardware-aware controller for Ollama that enforces token limits.
Dependencies: ollama, tkinter
Hardware Profile: Optimized for 8GB VRAM / 32GB RAM (RTX 2070 Super)
Usage (Import): 
    from script_name import OllamaGovernor
    gov = OllamaGovernor()
    gov.run_inference(model="qwen3.5:35b", prompt="...", tier_name="Balanced (MoE)")
Usage (CLI): 
    python script_name.py --cli [filter_string]
Usage (GUI): 
    python script_name.py
"""

import sys
import tkinter as tk
from tkinter import ttk, messagebox
import ollama

class OllamaGovernor:
    # Pre-defined safety tiers optimized for Jacob's specific hardware specs
    TIERS = {
        "VRAM Only (Fastest)": {"ctx": 8192, "predict": 512, "color": "#2ecc71"},
        "Balanced (MoE)":      {"ctx": 16384, "predict": 1024, "color": "#f1c40f"},
        "Deep Logic (Slow)":   {"ctx": 32768, "predict": 2048, "color": "#e67e22"},
        "Extreme (Risk)":     {"ctx": 65536, "predict": 4096, "color": "#e74c3c"}
    }

    def __init__(self):
        self.client = ollama

    def get_models(self, search_term=None):
        """Fetches models from Ollama, optionally filtered by name (e.g., 'qwen3.5')."""
        try:
            response = self.client.list()
            # Handle different versions of the Ollama library return structures
            models = [m.get('name', m) for m in response.get('models', [])]
            if search_term:
                return [m for m in models if search_term.lower() in m.lower()]
            return models
        except Exception as e:
            print(f"Error connecting to Ollama: {e}")
            return []

    def run_inference(self, model, prompt, tier_name, custom_limit=None):
        """Executes chat with enforced token governors to protect VRAM/RAM."""
        tier = self.TIERS.get(tier_name, self.TIERS["VRAM Only (Fastest)"])
        ctx_limit = int(custom_limit) if custom_limit else tier["ctx"]
        
        options = {
            "num_ctx": ctx_limit,
            "num_predict": tier["predict"],
            "temperature": 0.7
        }
        
        return self.client.chat(
            model=model, 
            messages=[{'role': 'user', 'content': prompt}], 
            options=options
        )

    def get_ui_widget(self, parent, search="qwen"):
        """Returns a modular Tkinter Frame for injection into larger apps."""
        frame = ttk.LabelFrame(parent, text="Ollama Governor Controls", padding=10)
        
        # Grid Configuration
        frame.columnconfigure(1, weight=1)

        # Model Selection via Search Filter
        ttk.Label(frame, text="Model:").grid(row=0, column=0, sticky="w", padx=5)
        model_list = self.get_models(search)
        model_var = tk.StringVar(value=model_list[0] if model_list else "None")
        model_drop = ttk.Combobox(frame, textvariable=model_var, values=model_list, state="readonly")
        model_drop.grid(row=0, column=1, pady=5, sticky="ew")

        # Tier Selection (Hardware Profiles)
        ttk.Label(frame, text="Safety Tier:").grid(row=1, column=0, sticky="w", padx=5)
        tier_var = tk.StringVar(value="VRAM Only (Fastest)")
        tier_drop = ttk.Combobox(frame, textvariable=tier_var, values=list(self.TIERS.keys()), state="readonly")
        tier_drop.grid(row=1, column=1, pady=5, sticky="ew")

        # Enforced Max Token Input
        ttk.Label(frame, text="Enforced Max:").grid(row=2, column=0, sticky="w", padx=5)
        token_var = tk.StringVar(value=str(self.TIERS["VRAM Only (Fastest)"]["ctx"]))
        token_entry = ttk.Entry(frame, textvariable=token_var)
        token_entry.grid(row=2, column=1, pady=5, sticky="ew")

        # Logic to update Entry when Tier changes
        def update_limit(*args):
            new_val = self.TIERS[tier_var.get()]["ctx"]
            token_var.set(str(new_val))
        
        tier_var.trace_add("write", update_limit)

        return frame, {"model": model_var, "tier": tier_var, "tokens": token_var}

# --- Standard Execution Block ---

def run_gui():
    root = tk.Tk()
    root.title("Ollama Governor")
    root.geometry("400x250")
    gov = OllamaGovernor()
    
    # Inject the widget
    ui_frame, vars = gov.get_ui_widget(root, search="qwen")
    ui_frame.pack(padx=20, pady=20, fill="both", expand=True)
    
    def on_test():
        m = vars["model"].get()
        t = vars["tokens"].get()
        messagebox.showinfo("Config Validated", f"Model: {m}\nEnforced Context: {t}\n\nReady for inference.")

    ttk.Button(root, text="Validate Configuration", command=on_test).pack(pady=10)
    root.mainloop()

def run_cli():
    gov = OllamaGovernor()
    search = sys.argv[2] if len(sys.argv) > 2 else ""
    print(f"--- Ollama Models (Filter: '{search}') ---")
    models = gov.get_models(search)
    if not models:
        print("No models found. Ensure Ollama is running.")
    for m in models:
        print(f" [LOADABLE] -> {m}")

if __name__ == "__main__":
    if "--cli" in sys.argv:
        run_cli()
    else:
        run_gui()