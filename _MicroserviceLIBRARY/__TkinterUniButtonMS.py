import tkinter as tk
from dataclasses import dataclass
from typing import Any, Dict, Optional, Callable

from microservice_std_lib import service_metadata, service_endpoint

# ==============================================================================
# CONFIGURATION MODELS
# ==============================================================================

@dataclass
class ButtonConfig:
    text: str
    command: Callable[[], None]
    bg_color: str
    active_bg_color: str
    fg_color: str = "#FFFFFF"

@dataclass
class LinkConfig:
    """Configuration for the 'Linked' state (The Trap)"""
    trap_bg: str = "#7C3AED"    # Deep Purple
    btn_bg: str = "#8B5CF6"     # Lighter Purple
    text_color: str = "#FFFFFF"

# ==============================================================================
# MICROSERVICE CLASS
# ==============================================================================

@service_metadata(
    name="LockingDualBtn",
    version="1.0.0",
    description="A unified button group (Left/Right/Link) where linking merges the actions.",
    tags=["ui", "widget", "button"],
    capabilities=["ui:gui"]
)
class TkinterUniButtonMS(tk.Frame):
    """
    A generic button group that can merge ANY two actions.
    Pass the visual/functional definitions in via the config objects.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        parent = self.config.get("parent")
        # Initialize tk.Frame
        super().__init__(parent)
        
        # Extract Button Configurations
        self.left_cfg: Optional[ButtonConfig] = self.config.get("left_btn")
        self.right_cfg: Optional[ButtonConfig] = self.config.get("right_btn")
        self.link_cfg: LinkConfig = self.config.get("link_config") or LinkConfig()
        
        self.is_linked = False
        
        # Attempt to get parent background for seamless look
        try:
            self.default_bg = parent.cget("bg")
        except AttributeError:
            self.default_bg = "#f0f0f0"

        if not self.left_cfg or not self.right_cfg:
            # Fallback for safe init if configs are missing
            print("Warning: TkinterUniButtonMS initialized without button configs.")
            return

        self._setup_ui()
        self._update_state()

    def _setup_ui(self):
        self.configure(padx=4, pady=4)
        
        common_style = {"relief": "flat", "font": ("Segoe UI", 10, "bold"), "bd": 0, "cursor": "hand2"}

        # 1. Left Button (Generic)
        self.btn_left = tk.Button(self, command=lambda: self._execute("left"), **common_style)
        self.btn_left.pack(side="left", fill="y", padx=(0, 2))

        # 2. Link Toggle (The Chain)
        self.btn_link = tk.Button(self, text="&", width=3, command=self._toggle_link, **common_style)
        self.btn_link.pack(side="left", fill="y", padx=(0, 2))

        # 3. Right Button (Generic)
        self.btn_right = tk.Button(self, command=lambda: self._execute("right"), **common_style)
        self.btn_right.pack(side="left", fill="y")

    def _toggle_link(self):
        self.is_linked = not self.is_linked
        self._update_state()

    def _update_state(self):
        if self.is_linked:
            # --- LINKED STATE (The Trap) ---
            self.configure(bg=self.link_cfg.trap_bg)
            
            # Both buttons look identical in the "Trap"
            for btn in (self.btn_left, self.btn_right, self.btn_link):
                btn.configure(bg=self.link_cfg.btn_bg, fg=self.link_cfg.text_color, activebackground=self.link_cfg.trap_bg)
            
            # Keep original text
            self.btn_left.configure(text=self.left_cfg.text)
            self.btn_right.configure(text=self.right_cfg.text)

        else:
            # --- INDEPENDENT STATE ---
            try: 
                self.configure(bg=self.default_bg)
            except: 
                self.configure(bg="#f0f0f0") 

            # Restore Left Button
            self.btn_left.configure(
                text=self.left_cfg.text, 
                bg=self.left_cfg.bg_color, 
                fg=self.left_cfg.fg_color,
                activebackground=self.left_cfg.active_bg_color
            )

            # Restore Right Button
            self.btn_right.configure(
                text=self.right_cfg.text, 
                bg=self.right_cfg.bg_color, 
                fg=self.right_cfg.fg_color,
                activebackground=self.right_cfg.active_bg_color
            )

            # Restore Link Button (Neutral Gray)
            self.btn_link.configure(bg="#E5E7EB", fg="#374151", activebackground="#D1D5DB")

    def _execute(self, source):
        if self.is_linked:
            # Chain them: Left then Right
            self.left_cfg.command()
            self.right_cfg.command()
        else:
            if source == "left": 
                self.left_cfg.command()
            elif source == "right": 
                self.right_cfg.command()


# --- Independent Test Block ---
if __name__ == "__main__":
    root = tk.Tk()
    root.title("UniButton Test")
    root.geometry("300x100")
    
    # Define actions
    def on_validate(): print("Validating Data...")
    def on_apply(): print("Applying Changes...")
    
    # Create Configs
    btn1 = ButtonConfig("Validate", on_validate, "#3b82f6", "#2563eb") # Blue
    btn2 = ButtonConfig("Apply", on_apply, "#10b981", "#059669")       # Green
    
    # Init Service
    svc = TkinterUniButtonMS({
        "parent": root, 
        "left_btn": btn1, 
        "right_btn": btn2
    })
    print("Service ready:", svc)
    svc.pack(pady=20)
    
    root.mainloop()