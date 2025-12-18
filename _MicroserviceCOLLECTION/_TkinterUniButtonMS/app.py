## Locking Dual Button - Instructions
# TO USE:
# In your main app file
# from components import UnifiedButtonGroup # assuming you saved the class there
# 
# def my_validation_logic():
#     # do pandas stuff, etc
#     pass
# 
# def my_apply_logic():
#    # do database stuff
#     pass
# 
# Drop the button group into your GUI
# my_buttons = UnifiedButtonGroup(
#     parent=my_frame, 
#     on_validate=my_validation_logic, 
#     on_apply=my_apply_logic
# )
# my_buttons.pack()
## 

import tkinter as tk
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from microservice_std_lib import service_metadata, service_endpoint

@dataclass
class ButtonConfig:
    text: str
    command: callable
    bg_color: str
    active_bg_color: str
    fg_color: str = "#FFFFFF"

@dataclass
class LinkConfig:
    """Configuration for the 'Linked' state (The Trap)"""
    trap_bg: str = "#7C3AED"    # Deep Purple
    btn_bg: str = "#8B5CF6"     # Lighter Purple
    text_color: str = "#FFFFFF"

@service_metadata(
name="LockingDualBtn",
version="1.0.0",
description="A unified button group (Left/Right/Link) where linking merges the actions.",
tags=["ui", "widget", "button"],
capabilities=["ui:gui"]
)
class LockingDualBtnMS(tk.Frame):
"""
A generic button group that can merge ANY two actions.
Pass the visual/functional definitions in via the config objects.
"""
def __init__(self, config: Optional[Dict[str, Any]] = None):
self.config = config or {}
parent = self.config.get("parent")
super().__init__(parent)
        
self.left_cfg = self.config.get("left_btn")
self.right_cfg = self.config.get("right_btn")
self.link_cfg = self.config.get("link_config") or LinkConfig()
        
        self.is_linked = False
        self.default_bg = parent.cget("bg") # Fallback to parent background

        self._setup_ui()
        self._update_state()

    def _setup_ui(self):
        self.config(padx=4, pady=4)
        
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
            self.config(bg=self.link_cfg.trap_bg)
            
            # Both buttons look identical in the "Trap"
            for btn in (self.btn_left, self.btn_right, self.btn_link):
                btn.config(bg=self.link_cfg.btn_bg, fg=self.link_cfg.text_color, activebackground=self.link_cfg.trap_bg)
            
            # Keep original text
            self.btn_left.config(text=self.left_cfg.text)
            self.btn_right.config(text=self.right_cfg.text)

        else:
            # --- INDEPENDENT STATE ---
            try: self.config(bg=self.default_bg)
            except: self.config(bg="#f0f0f0") 

            # Restore Left Button
            self.btn_left.config(
                text=self.left_cfg.text, 
                bg=self.left_cfg.bg_color, 
                fg=self.left_cfg.fg_color,
                activebackground=self.left_cfg.active_bg_color
            )

            # Restore Right Button
            self.btn_right.config(
                text=self.right_cfg.text, 
                bg=self.right_cfg.bg_color, 
                fg=self.right_cfg.fg_color,
                activebackground=self.right_cfg.active_bg_color
            )

            # Restore Link Button (Neutral Gray)
            self.btn_link.config(bg="#E5E7EB", fg="#374151", activebackground="#D1D5DB")

    def _execute(self, source):
        if self.is_linked:
            # Chain them: Left then Right
            self.left_cfg.command()
            self.right_cfg.command()
        else:
        if source == "left": self.left_cfg.command()
        elif source == "right": self.right_cfg.command()

        if __name__ == "__main__":
        root = tk.Tk()
        btn1 = ButtonConfig("Save", lambda: print("Save"), "#444", "#555")
        btn2 = ButtonConfig("Run", lambda: print("Run"), "#444", "#555")
        svc = LockingDualBtnMS({"parent": root, "left_btn": btn1, "right_btn": btn2})
        print("Service ready:", svc)
        svc.pack(pady=20)
        root.mainloop()
