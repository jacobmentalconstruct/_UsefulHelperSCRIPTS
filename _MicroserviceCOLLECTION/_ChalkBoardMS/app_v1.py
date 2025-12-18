import tkinter as tk
from tkinter import font, ttk, colorchooser
import colorsys
import math
import random
import time
from typing import Any, Dict, Optional

# Assuming these exist in your environment. 
# If testing standalone without the lib, comment out the decorator and import.
try:
    from microservice_std_lib import service_metadata, service_endpoint
except ImportError:
    # Mocking for standalone functionality if lib is missing
    def service_metadata(**kwargs):
        def decorator(cls):
            return cls
        return decorator

    def service_endpoint(**kwargs):
        def decorator(func):
            return func
        return decorator

@service_metadata(
    name="Chalkboard",
    version="1.1.0",
    description="Interactive digital signage/chalkboard widget with retro themes.",
    tags=["ui", "visuals", "widget"],
    capabilities=["ui:gui"]
)
class ChalkboardMS(tk.Frame):
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        parent = self.config.get("parent")
        super().__init__(parent)
        
        # --- CONFIGURATION ---
        self.bg_color = "#050505"
        self.configure(bg=self.bg_color)
        
        # Resolving root for bindings
        self.root = self.winfo_toplevel()
        if parent is None: 
            self.root.title("OBS Rad-IO Signboard")
            self.root.geometry("900x600")
            self.root.configure(bg="#111")
        
        # --- STATE ---
        self.text_content = "ON AIR"
        self.saved_state = {} 
        
        # Cursor State
        self.cursor_visible = True
        self.cursor_blink_state = True
        self.last_activity_time = time.time()
        
        # Animation / Action State
        self.action_active = False
        self.action_start_time = 0
        self.action_type = None 
        self.restore_timer = None 
        
        # Window State
        self.settings_window = None 
        
        # Appearance Defaults
        self.text_color = "#f4f4f4" 
        self.shadow_color = "#000000"
        self.neon_stroke_color = "#FF00FF" # Magenta default
        self.neon_fill_color = "#FFFFFF"
        
        # Font State
        self.base_font_size = 80
        self.current_font_size = 80
        self.scale_factor = 1.0
        self.font_family = "Arial"
        self.is_bold = True
        self.is_italic = False
        self.is_underline = False
        
        # Style Mode
        self.render_style = "neon" # Default to the coolest one
        
        # Spinner State
        self.spinner_active = False
        self.spinner_hue = 0.0
        self.spin_angle_1 = 0
        self.spin_angle_2 = 0
        self.spin_angle_3 = 0

        self._detect_system_fonts()

        # --- UI LAYOUT ---
        self.canvas = tk.Canvas(self, bg=self.bg_color, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        
        # Control Deck (The Mixer Board Look)
        self.frm_actions = tk.Frame(self, bg="#1a1a1a", height=50, bd=2, relief="raised")
        self.frm_actions.pack(fill="x", side="bottom")
        
        self.btn_settings = tk.Button(
            self, text="⚙", font=("Segoe UI", 12), 
            bg=self.bg_color, fg="#444", borderwidth=0, 
            command=self.open_settings, cursor="hand2"
        )
        self.btn_settings.place(relx=1.0, rely=0.0, anchor="ne", x=-5, y=5)

        # --- INITIALIZE ACTIONS ---
        self._build_action_buttons()

        # --- BINDINGS ---
        self.root.bind("<Key>", self.handle_keypress)
        self.root.bind("<Button-1>", self.handle_click)
        self.root.bind("<Configure>", self.on_resize)
        
        self.root.bind("<Shift-MouseWheel>", self.on_scale_scroll)
        self.root.bind("<Shift-Button-4>", lambda e: self.on_scale_scroll(e, 1))
        self.root.bind("<Shift-Button-5>", lambda e: self.on_scale_scroll(e, -1))
        
        # Theme Hotkeys (From your HTML file)
        self.root.bind("<F1>", lambda e: self.apply_theme("neon"))
        self.root.bind("<F2>", lambda e: self.apply_theme("terminal"))
        self.root.bind("<F3>", lambda e: self.apply_theme("chalk"))

        # Start Loops
        self.blink_cursor_loop()
        self.animate_loop()
        
        # Apply default theme
        self.apply_theme("neon")

    def _detect_system_fonts(self):
        system_fonts = font.families()
        self.font_family = "Arial"
        # Prioritize retro/display fonts
        preferred = ["Impact", "Press Start 2P", "Consolas", "Courier New", "Comic Sans MS", "Segoe UI Black"]
        for p in preferred:
            if p in system_fonts:
                self.font_family = p
                # Don't break immediately, we might find a better one later in the list? 
                # Actually let's just grab the first hit for now.
                break

    def _build_action_buttons(self):
        # Create a "Bank" of buttons style
        lbl = tk.Label(self.frm_actions, text="FX BANK:", bg="#1a1a1a", fg="#666", font=("Arial", 8, "bold"))
        lbl.pack(side="left", padx=(10, 5))

        def create_fx_btn(text, color, cmd):
            btn = tk.Button(
                self.frm_actions, 
                text=text, font=("Impact", 12),
                bg="#333", fg=color, 
                activebackground=color, activeforeground="#000",
                relief="raised", bd=1,
                command=lambda: [self.handle_click(None), cmd()],
                cursor="hand2", width=6
            )
            btn.pack(side="left", padx=5, pady=8)
            return btn

        self.btn_spin = create_fx_btn("◎ LOOP", "#00FF00", self.toggle_spinner)
        create_fx_btn("BOOM", "#FF4400", lambda: self.trigger_action("BOOM!", "#FF4400", "boom"))
        create_fx_btn("POW", "#FFFF00", lambda: self.trigger_action("POW!", "#FFFF00", "pow"))
        create_fx_btn("ZAP", "#00FFFF", lambda: self.trigger_action("ZAP!", "#00FFFF", "zap"))
        
        # Helper text
        info = tk.Label(self.frm_actions, text="[F1:Neon | F2:Hack | F3:Chalk]", bg="#1a1a1a", fg="#444", font=("Consolas", 8))
        info.pack(side="right", padx=10)

    # --- THEME ENGINE ---
    def apply_theme(self, theme_name):
        if theme_name == "neon":
            self.bg_color = "#050505"
            self.text_color = "#FFFFFF"
            self.neon_stroke_color = "#bc13fe" # Purple/Pink
            self.render_style = "neon"
            self.font_family = "Impact" if "Impact" in font.families() else "Arial"
            
        elif theme_name == "terminal":
            self.bg_color = "#000000"
            self.text_color = "#00ff41" # Matrix Green
            self.render_style = "normal"
            self.font_family = "Courier New"
            # Simulate scanlines in bg color? Hard in tk, keeping it black.
            
        elif theme_name == "chalk":
            self.bg_color = "#2b3a28" # Dark Green
            self.text_color = "#f4f4f4"
            self.render_style = "shaky" # Rough look
            self.font_family = "Comic Sans MS" if "Comic Sans MS" in font.families() else "Arial"

        self.canvas.config(bg=self.bg_color)
        self.frm_actions.config(bg="#1a1a1a")
        
    # --- LOGIC ---

    def toggle_spinner(self):
        self.spinner_active = not self.spinner_active
        if self.spinner_active:
            self.btn_spin.config(fg="#000", bg="#00FF00", text="ON")
        else:
            self.btn_spin.config(fg="#00FF00", bg="#333", text="◎ LOOP")

    @service_endpoint(
        inputs={"text": "str", "color": "str", "action_type": "str"},
        outputs={},
        description="Triggers a visual effect (BOOM, POW, ZAP).",
        tags=["ui", "effect"],
        side_effects=["ui:update"]
    )
    def trigger_action(self, text, color, action_type):
        if self.restore_timer:
            self.root.after_cancel(self.restore_timer)
            self.restore_timer = None
        else:
            self.saved_state = {
                "text": self.text_content,
                "color": self.text_color,
                "style": self.render_style,
                "font": self.font_family,
                "bold": self.is_bold
            }
        
        self.action_active = True
        self.action_start_time = time.time()
        self.action_type = action_type
        self.text_content = text
        self.text_color = color
        self.render_style = "comic"
        
        sys_fonts = font.families()
        if action_type == "boom" and "Impact" in sys_fonts: self.font_family = "Impact"
        elif action_type == "pow" and "Comic Sans MS" in sys_fonts: self.font_family = "Comic Sans MS"
        elif action_type == "zap": self.font_family = "Courier New"
        
        self.restore_timer = self.root.after(1500, self._restore_state)
        
    def _restore_state(self):
        if not self.saved_state: return
        self.text_content = self.saved_state["text"]
        self.text_color = self.saved_state["color"]
        self.render_style = self.saved_state["style"]
        self.font_family = self.saved_state["font"]
        self.is_bold = self.saved_state["bold"]
        
        self.action_active = False
        self.restore_timer = None
        self.current_font_size = self.base_font_size

    def update_animation_physics(self):
        if not self.action_active:
            self.current_font_size = self.base_font_size
            return

        elapsed = time.time() - self.action_start_time
        
        if self.action_type == "boom":
            progress = min(elapsed * 3, 1.5)
            scale = 0.5 + progress
            self.current_font_size = int(self.base_font_size * scale)
            self.is_bold = True
            
        elif self.action_type == "pow":
            pulse = math.sin(elapsed * 10) * 0.3
            scale = 1.2 + pulse
            self.current_font_size = int(self.base_font_size * scale)
            self.is_bold = (int(elapsed * 10) % 2 == 0)
            
        elif self.action_type == "zap":
            jitter = random.uniform(0.8, 1.4)
            self.current_font_size = int(self.base_font_size * jitter)
            self.is_bold = True

    # --- INPUT HANDLING ---

    def handle_click(self, event):
        self.last_activity_time = time.time()
        self.cursor_blink_state = True
        self.cursor_visible = True
        self.root.focus_set()

    def handle_keypress(self, event):
        self.last_activity_time = time.time()
        # Ignore function keys
        if event.keysym in ["F1", "F2", "F3", "F4", "F5", "Shift_L", "Shift_R", "Control_L", "Alt_L"]: return
        
        if isinstance(event.widget, (tk.Entry, tk.Listbox, ttk.Combobox)): return
        
        if event.keysym == "BackSpace": 
            self.text_content = self.text_content[:-1]
        elif event.keysym == "Escape": 
            self.text_content = ""
        elif event.keysym == "Return":
             # Optional: Clear on enter or add newline? Let's clear for now as it's a signboard
             pass 
        elif len(event.char) == 1 and ord(event.char) >= 32: 
            self.text_content += event.char

    def on_scale_scroll(self, event, direction=None):
        self.last_activity_time = time.time()
        delta = direction if direction else (1 if event.delta > 0 else -1)
        if delta > 0: self.base_font_size += 5
        else: self.base_font_size = max(10, self.base_font_size - 5)

    # --- RENDERING ENGINE ---

    def get_font_tuple(self):
        style_list = []
        if self.is_bold: style_list.append("bold")
        if self.is_italic: style_list.append("italic")
        if self.is_underline: style_list.append("underline")
        size = int(self.current_font_size * self.scale_factor)
        return (self.font_family, size, " ".join(style_list))

    def blink_cursor_loop(self):
        self.cursor_blink_state = not self.cursor_blink_state
        self.root.after(600, self.blink_cursor_loop)

    def animate_loop(self):
        # 1. Activity Check
        time_since_activity = time.time() - self.last_activity_time
        
        # --- SAFE FOCUS CHECK ---
        try:
            is_focused = self.root.focus_displayof() is not None
        except Exception:
            is_focused = False
            
        self.cursor_visible = (is_focused and time_since_activity < 5.0 and self.cursor_blink_state)

        # 2. Physics Update
        self.update_animation_physics()

        # 3. Draw
        self.draw_frame()
        self.root.after(16, self.animate_loop)

    def draw_frame(self):
        self.canvas.delete("all")
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        cx, cy = w / 2, h / 2

        # SPINNER
        if self.spinner_active:
            self._draw_spinner(cx, cy, min(w, h))

        # TEXT
        display_text = self.text_content + ("_" if self.cursor_visible and not self.action_active else "")
        current_font = self.get_font_tuple()

        if self.render_style == "neon":
            # Simulate Glow with stacked offsets
            glow_color = self.neon_stroke_color
            
            # Deep glow (blurry)
            for i in range(1, 4):
                 self.canvas.create_text(cx, cy, text=display_text, fill=glow_color, font=current_font)
            
            # Offset Glitch Effect (subtle vibration)
            if random.random() > 0.95:
                ox = random.randint(-3, 3)
                self.canvas.create_text(cx+ox, cy, text=display_text, fill="#FFFFFF", font=current_font)
            else:
                self.canvas.create_text(cx, cy, text=display_text, fill="#FFFFFF", font=current_font)

        elif self.render_style == "comic":
            # Pop Art Shadow
            depth = max(3, self.current_font_size // 10)
            for i in range(depth, 0, -1):
                self.canvas.create_text(cx+i, cy+i, text=display_text, fill="#000", font=current_font)
            self.canvas.create_text(cx, cy, text=display_text, fill=self.text_color, font=current_font)
            self.canvas.create_text(cx-2, cy-2, text=display_text, fill="#FFFFFF", font=current_font)
            self.canvas.create_text(cx-2, cy-2, text=display_text, fill=self.text_color, font=current_font)
            
        elif self.render_style == "shaky":
            # Nervous / Chalk style
            ox = random.randint(-1, 1)
            oy = random.randint(-1, 1)
            self.canvas.create_text(cx+ox, cy+oy, text=display_text, fill=self.text_color, font=current_font)
            
        else: # Normal / Terminal
            self.canvas.create_text(cx, cy, text=display_text, fill=self.text_color, font=current_font)

    def _draw_spinner(self, cx, cy, min_dim):
        base_size = min_dim / 2
        self.spinner_hue = (self.spinner_hue + 0.005) % 1.0
        def get_col(offset):
            r, g, b = colorsys.hsv_to_rgb((self.spinner_hue + offset)%1.0, 1.0, 1.0)
            return f'#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}'

        c1 = get_col(0.0)
        c2 = get_col(0.3)
        
        # Draw dynamic rings
        self.spin_angle_1 -= 3
        self.canvas.create_arc(cx-base_size*0.8, cy-base_size*0.8, cx+base_size*0.8, cy+base_size*0.8, 
                               start=self.spin_angle_1, extent=120, outline=c1, width=10, style="arc")
        self.canvas.create_arc(cx-base_size*0.8, cy-base_size*0.8, cx+base_size*0.8, cy+base_size*0.8, 
                               start=self.spin_angle_1+180, extent=120, outline=c1, width=10, style="arc")

        self.spin_angle_2 += 5
        self.canvas.create_arc(cx-base_size*0.6, cy-base_size*0.6, cx+base_size*0.6, cy+base_size*0.6, 
                               start=self.spin_angle_2, extent=250, outline=c2, width=6, style="arc")

    def on_resize(self, event):
        # Redraw background if needed
        pass

    # --- SETTINGS WINDOW ---
    def open_settings(self):
        if self.settings_window and tk.Toplevel.winfo_exists(self.settings_window):
            self.settings_window.lift()
            return

        win = tk.Toplevel(self.root)
        self.settings_window = win
        win.title("Settings")
        win.geometry("300x400")
        win.configure(bg="#222")
        
        def add_btn(txt, cmd):
            tk.Button(win, text=txt, command=cmd, bg="#333", fg="#FFF").pack(fill="x", padx=20, pady=5)

        tk.Label(win, text="Settings", font=("Arial", 14, "bold"), bg="#222", fg="#FFF").pack(pady=10)
        
        add_btn("Pick Neon Color", self._pick_neon_color)
        add_btn("Close", win.destroy)

    def _pick_neon_color(self):
        c = colorchooser.askcolor(self.neon_stroke_color)[1]
        if c: 
            self.neon_stroke_color = c
            self.apply_theme("neon")

if __name__ == "__main__":
    root = tk.Tk()
    app = ChalkboardMS({"parent": root})
    app.pack(fill="both", expand=True)
    root.mainloop()