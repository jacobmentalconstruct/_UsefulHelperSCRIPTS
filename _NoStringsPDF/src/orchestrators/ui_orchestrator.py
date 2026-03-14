"""
ORCHESTRATOR: UI Orchestrator
DESCRIPTION: Manages the layout, events, dialogs, and async loading states.
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, Menu
import threading
import math
import time
import os
import colorsys  # <--- Added for Neon effects
from src.microservices._TkinterButtonMS import TkinterButtonMS

class MainUIOrchestrator:
    def __init__(self, root, shell, theme_mgr, engine):
        self.root = root
        self.shell = shell
        self.theme_mgr = theme_mgr
        self.engine = engine
        self.colors = self.theme_mgr.get_theme()
        
        self.state = {
            "zoom": 1.0,
            "page_idx": 0,
            "total_pages": 0,
            "file_path": None,
            "thumb_size": 180,
            "grid_cols": 1
        }
        
        # Image Tracking
        self.thumbnail_widgets = [] 
        self.thumbnail_images = []
        
        # Main View Tracking
        self.main_image_item = None
        self.current_img_w = 0
        self.current_img_h = 0
        
        # Drag Data
        self.drag_data = {
            "source_idx": None, 
            "ghost_window": None,
            "indicator": None,
            "indicator_active": False,
            "drop_target_idx": None
        }

        # LOADING OVERLAY STATE
        self.loading_overlay = None
        self.spinner_running = False
        self.spinner_state = { "a1": 0, "a2": 0, "a3": 0, "hue": 0 } # <--- State for ThingyMaBobber
        
        self._build_layout()
        self._build_toolbar()
        self._build_context_menu()
        self._bind_hotkeys()

    def _build_layout(self):
        container = self.shell.get_main_container()
        
        self.toolbar_frame = tk.Frame(container, bg=self.colors['panel_bg'], height=40)
        self.toolbar_frame.pack(side="top", fill="x", pady=(0, 2))
        
        self.paned = tk.PanedWindow(container, orient=tk.HORIZONTAL, bg=self.colors['border'], sashwidth=4)
        self.paned.pack(fill="both", expand=True)
        
        # Left Panel
        self.left_container = tk.Frame(self.paned, bg=self.colors['panel_bg'], width=300)
        self.paned.add(self.left_container, minsize=200)
        
        self.thumb_canvas = tk.Canvas(self.left_container, bg=self.colors['panel_bg'], highlightthickness=0)
        self.thumb_scroll = ttk.Scrollbar(self.left_container, orient="vertical", command=self.thumb_canvas.yview)
        self.thumb_frame = tk.Frame(self.thumb_canvas, bg=self.colors['panel_bg'])
        
        self.thumb_canvas.configure(yscrollcommand=self.thumb_scroll.set)
        self.thumb_scroll.pack(side="right", fill="y")
        self.thumb_canvas.pack(side="left", fill="both", expand=True)
        self.thumb_window_id = self.thumb_canvas.create_window((0,0), window=self.thumb_frame, anchor="nw")
        
        # Right Panel
        self.right_panel = tk.Frame(self.paned, bg="#525252")
        self.paned.add(self.right_panel, minsize=400)
        
        self.canvas = tk.Canvas(self.right_panel, bg="#525252", highlightthickness=0)
        self.v_scroll = ttk.Scrollbar(self.right_panel, orient="vertical", command=self.canvas.yview)
        self.h_scroll = ttk.Scrollbar(self.right_panel, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.v_scroll.set, xscrollcommand=self.h_scroll.set)
        
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.v_scroll.grid(row=0, column=1, sticky="ns")
        self.h_scroll.grid(row=1, column=0, sticky="ew")
        self.right_panel.grid_rowconfigure(0, weight=1)
        self.right_panel.grid_columnconfigure(0, weight=1)
        
        # Bindings
        self.thumb_frame.bind("<Configure>", self._on_thumb_frame_configure)
        self.thumb_canvas.bind("<Configure>", self._on_sidebar_resize)
        self.canvas.bind("<Configure>", self._on_main_view_resize)
        self.canvas.bind("<Button-3>", self._show_context_menu)
        
        self.root.bind_all("<MouseWheel>", self._dispatch_scroll)
        self.root.bind_all("<Button-4>", self._dispatch_scroll) 
        self.root.bind_all("<Button-5>", self._dispatch_scroll)

    def _bind_hotkeys(self):
        self.root.bind("<Left>", lambda e: self._prev_page())
        self.root.bind("<Right>", lambda e: self._next_page())
        self.root.bind("<Delete>", lambda e: self._action_delete_page())

    def _build_toolbar(self):
        def add_btn(text, cmd, icon_name=None, side="left"):
            icon_path = f"assets/{icon_name}.png" if icon_name else None
            btn = TkinterButtonMS(self.toolbar_frame, text=text, command=cmd, icon_path=icon_path, theme=self.colors)
            btn.pack(side=side, padx=2, pady=4)
        
        add_btn("OPEN", self._action_open, "open")
        add_btn("INSERT", self._action_insert_file, "insert")
        add_btn("INTERLEAVE", self._show_interleave_dialog, "interleave")
        
        tk.Frame(self.toolbar_frame, bg=self.colors['panel_bg'], width=15).pack(side="left")
        
        add_btn("EXTRACT", self._show_extract_dialog, "extract")
        add_btn("SPLIT", self._show_split_dialog, "split") 
        add_btn("EXPORT", self._show_compression_dialog, "save")
        
        tk.Frame(self.toolbar_frame, bg=self.colors['panel_bg'], width=15).pack(side="left")
        
        add_btn("", lambda: self._action_rotate(False), "rot_l") 
        add_btn("", lambda: self._action_rotate(True), "rot_r")
        
        tk.Frame(self.toolbar_frame, bg=self.colors['panel_bg'], width=15).pack(side="left")
        
        add_btn("", lambda: self._change_main_zoom(-0.2), "zoom_out")
        add_btn("", lambda: self._change_main_zoom(0.2), "zoom_in")
        
        add_btn("", self._next_page, "next", side="right")
        add_btn("", self._prev_page, "prev", side="right")

    def _build_context_menu(self):
        self.context_menu = Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Rotate CW", command=lambda: self._action_rotate(True))
        self.context_menu.add_command(label="Rotate CCW", command=lambda: self._action_rotate(False))
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Delete Page", command=self._action_delete_page)

    def _show_context_menu(self, event):
        self.context_menu.post(event.x_root, event.y_root)

    # --- ACTIONS ---

    def _action_open(self):
        path = filedialog.askopenfilename(filetypes=[("PDF Files", "*.pdf")])
        if path:
            def load(): return self.engine.load_pdf(path)
            def done(count):
                self._hide_loading()
                self.state["total_pages"] = count
                self.state["file_path"] = path
                self.state["page_idx"] = 0
                filename = os.path.basename(path)
                self.root.title(f"{filename} - NoStringsPDF")
                self._render_current_page()
                self._regenerate_thumbnails()
            self._run_async(load, done, message="Loading PDF...")

    def _action_delete_page(self):
        if not self.state["file_path"]: return
        idx = self.state["page_idx"]
        if messagebox.askyesno("Confirm", f"Delete Page {idx+1}?"):
            s, n = self.engine.delete_page(idx)
            if s:
                self.state["total_pages"] = n
                if self.state["page_idx"] >= n: self.state["page_idx"] = max(0, n - 1)
                self._regenerate_thumbnails()
                self._render_current_page()

    def _action_insert_file(self):
        if not self.state["file_path"]: return messagebox.showwarning("Warning", "Open PDF first.")
        path = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        if not path: return
        at = self.state["page_idx"] + 1
        def on_done(res):
            success, count = res
            self._hide_loading()
            if success:
                self.state["total_pages"] = count
                self._regenerate_thumbnails()
                self.state["page_idx"] = at
                self._render_current_page()
                messagebox.showinfo("Done", "File inserted.")
        self._run_async(self.engine.insert_file, on_done, path, at, message="Inserting File...")

    def _show_interleave_dialog(self):
        if not self.state["file_path"]: return messagebox.showwarning("Warning", "Open first PDF.")
        path_b = filedialog.askopenfilename(title="Select Second PDF", filetypes=[("PDF", "*.pdf")])
        if not path_b: return
        rev = messagebox.askyesno("Reverse?", "Reverse second file order?")
        def on_done(res):
            success, count = res
            self._hide_loading()
            if success:
                self.state["total_pages"] = count
                self.state["page_idx"] = 0
                self._regenerate_thumbnails()
                self._render_current_page()
                messagebox.showinfo("Done", "Interleaved successfully.")
            else: messagebox.showerror("Error", "Failed.")
        self._run_async(self.engine.interleave_file, on_done, path_b, rev, message="Interleaving Docs...")

    def _action_rotate(self, clockwise):
        if not self.state["file_path"]: return
        self.engine.rotate_page(self.state["page_idx"], clockwise)
        self._render_current_page()
        self._update_single_thumbnail(self.state["page_idx"])

    def _show_split_dialog(self):
        if not self.state["file_path"]: return messagebox.showwarning("No File", "Open PDF first.")
        dlg = tk.Toplevel(self.root)
        dlg.title("Smart Split"); dlg.geometry("400x220"); dlg.configure(bg="#2d2d2d")
        tk.Label(dlg, text="Split into Chunks", bg="#2d2d2d", fg="white", font=("Arial", 12)).pack(pady=10)
        tk.Label(dlg, text="Max Size (MB):", bg="#2d2d2d", fg="#aaa").pack()
        e = tk.Entry(dlg, width=10); e.insert(0,"5"); e.pack(pady=5)
        def run():
            try: mb = int(e.get())
            except: return
            path = filedialog.asksaveasfilename(title="Base Name", filetypes=[("PDF","*.pdf")])
            if path:
                def task(): return self.engine.save_split_by_size(path, mb)
                def done(res):
                    self._hide_loading()
                    if res[0]: messagebox.showinfo("Success", f"Created {len(res[1])} files.")
                    else: messagebox.showerror("Error", str(res[1]))
                self._run_async(task, done, message="Splitting PDF...")
                dlg.destroy()
        TkinterButtonMS(dlg, text="SPLIT", command=run, theme=self.colors).pack(fill="x", padx=60, pady=20)

    def _show_extract_dialog(self):
        if not self.state["file_path"]: return messagebox.showwarning("No File", "Open PDF first.")
        dlg = tk.Toplevel(self.root)
        dlg.title("Extract"); dlg.geometry("400x250"); dlg.configure(bg="#2d2d2d")
        tk.Label(dlg, text="Page Range (e.g. 1, 3-5):", bg="#2d2d2d", fg="white").pack(pady=20)
        e = tk.Entry(dlg, width=40); e.pack()
        def run():
            s = e.get()
            if not s: return
            path = filedialog.asksaveasfilename(filetypes=[("PDF","*.pdf")])
            if path:
                def done(res):
                    self._hide_loading()
                    if res[0]: messagebox.showinfo("Saved", res[1])
                    else: messagebox.showerror("Error", res[1])
                self._run_async(self.engine.save_subset, done, path, s, message="Extracting Pages...")
                dlg.destroy()
        TkinterButtonMS(dlg, text="SAVE", command=run, theme=self.colors).pack(fill="x", padx=40, pady=20)

    def _show_compression_dialog(self):
        if not self.state["file_path"]: return messagebox.showwarning("No File", "Open PDF first.")
        dlg = tk.Toplevel(self.root)
        dlg.title("Advanced Export"); dlg.geometry("400x550"); dlg.configure(bg="#2d2d2d")
        vars = { "optimize": tk.BooleanVar(value=True), "dpi": tk.IntVar(value=150), 
                 "quality": tk.IntVar(value=75), "grayscale": tk.BooleanVar(value=False), 
                 "flatten": tk.BooleanVar(value=True), "masks": tk.BooleanVar(value=False), 
                 "dedup": tk.BooleanVar(value=True), "stream": tk.BooleanVar(value=True) }
        tk.Label(dlg, text="Optimization Settings", bg="#2d2d2d", fg="white").pack(pady=10)
        f1 = tk.LabelFrame(dlg, text="Images", bg="#2d2d2d", fg="white"); f1.pack(fill="x", padx=10)
        tk.Checkbutton(f1, text="Optimize Images", variable=vars["optimize"], bg="#2d2d2d", fg="#ccc", selectcolor="#444").pack(anchor="w")
        tk.Scale(f1, variable=vars["dpi"], from_=50, to=300, orient="horizontal", label="DPI", bg="#2d2d2d", fg="white").pack(fill="x")
        tk.Scale(f1, variable=vars["quality"], from_=10, to=100, orient="horizontal", label="Quality", bg="#2d2d2d", fg="white").pack(fill="x")
        tk.Checkbutton(f1, text="Grayscale", variable=vars["grayscale"], bg="#2d2d2d", fg="#ccc", selectcolor="#444").pack(anchor="w")
        def run():
            path = filedialog.asksaveasfilename(filetypes=[("PDF","*.pdf")])
            if path:
                settings = {k: v.get() for k,v in vars.items()}
                def done(res):
                    self._hide_loading()
                    if res: messagebox.showinfo("Saved", f"Saved to {path}")
                    else: messagebox.showerror("Error", "Save failed.")
                self._run_async(self.engine.save_advanced, done, path, settings, message="Compressing...")
                dlg.destroy()
        TkinterButtonMS(dlg, text="EXPORT", command=run, theme=self.colors).pack(fill="x", padx=20, pady=20)

    # --- SCROLL & NAV ---

    def _get_target_panel(self, widget):
        curr = widget
        while curr:
            if curr == self.left_container or curr == self.thumb_canvas or curr == self.thumb_frame: return "LEFT"
            if curr == self.right_panel or curr == self.canvas: return "RIGHT"
            if curr == self.root: break
            curr = curr.master
        return "UNKNOWN"

    def _dispatch_scroll(self, event):
        delta = 0
        if event.num == 5 or event.delta < 0: delta = -1 
        if event.num == 4 or event.delta > 0: delta = 1 
        
        x, y = self.root.winfo_pointerxy()
        target = self.root.winfo_containing(x, y)
        if not target: return
        panel = self._get_target_panel(target)
        is_shift = (event.state & 0x0001) or (event.state & 0x0004)
        
        if panel == "LEFT":
            if is_shift: self._change_thumb_size(20 if delta > 0 else -20)
            else: self.thumb_canvas.yview_scroll(int(-1 * delta), "units")
        elif panel == "RIGHT":
            if is_shift: 
                self._change_main_zoom(0.2 if delta > 0 else -0.2)
            else:
                top, bottom = self.canvas.yview()
                at_top, at_bottom = (top <= 0.001), (bottom >= 0.999)
                content_fits = at_top and at_bottom
                if delta < 0: # Down
                    if at_bottom or content_fits: self._next_page()
                    else: self.canvas.yview_scroll(1, "units")
                else: # Up
                    if at_top or content_fits: self._prev_page()
                    else: self.canvas.yview_scroll(-1, "units")

    def _next_page(self):
        if self.state["page_idx"] < self.state["total_pages"] - 1:
            self.state["page_idx"] += 1
            self._render_current_page()

    def _prev_page(self):
        if self.state["page_idx"] > 0:
            self.state["page_idx"] -= 1
            self._render_current_page()

    # --- VIEWERS ---

    def _render_current_page(self):
        if not self.state["file_path"]: return
        img, w, h = self.engine.render_page(self.state["page_idx"], self.state["zoom"])
        self.canvas.image = img 
        self.current_img_w = w; self.current_img_h = h
        self.canvas.delete("all")
        self.main_image_item = self.canvas.create_image(0, 0, image=img, anchor="center")
        self.canvas.yview_moveto(0) 
        self._reflow_main_view()

    def _reflow_main_view(self):
        if not self.main_image_item or not self.canvas.image: return
        cw = self.canvas.winfo_width(); ch = self.canvas.winfo_height()
        iw = self.current_img_w + 40; ih = self.current_img_h + 40
        x = max(cw, iw) // 2; y = max(ch, ih) // 2
        self.canvas.coords(self.main_image_item, x, y)
        self.canvas.configure(scrollregion=(0, 0, max(cw, iw), max(ch, ih)))

    def _on_main_view_resize(self, event):
        self._reflow_main_view()

    # --- THUMBNAILS ---
    def _update_single_thumbnail(self, idx):
        if idx < 0 or idx >= len(self.thumbnail_widgets): return
        box_size = self.state["thumb_size"]
        img, w, h = self.engine.render_thumbnail_fit(idx, max_size=(box_size, box_size))
        self.thumbnail_images[idx] = img
        cell = self.thumbnail_widgets[idx]
        for child in cell.winfo_children():
            if isinstance(child, tk.Frame):
                for grandchild in child.winfo_children():
                    if isinstance(grandchild, tk.Label) and grandchild.cget("text") == "":
                        grandchild.configure(image=img)
                        return

    def _change_main_zoom(self, delta):
        self.state["zoom"] = max(0.2, min(5.0, self.state["zoom"] + delta))
        self._render_current_page()

    def _change_thumb_size(self, delta):
        new_s = max(80, min(400, self.state["thumb_size"] + delta))
        if new_s != self.state["thumb_size"]:
            self.state["thumb_size"] = new_s
            self._regenerate_thumbnails()

    def _regenerate_thumbnails(self):
        for w in self.thumb_frame.winfo_children(): w.destroy()
        self.thumbnail_widgets = []
        self.thumbnail_images = []
        try:
            for i in range(self.state["total_pages"]):
                box_size = self.state["thumb_size"]
                img, w, h = self.engine.render_thumbnail_fit(i, max_size=(box_size, box_size))
                self.thumbnail_images.append(img)
                cell = tk.Frame(self.thumb_frame, bg=self.colors['panel_bg'], width=box_size+20, height=box_size+40)
                cell.pack_propagate(False) 
                inner = tk.Frame(cell, bg=self.colors['panel_bg'])
                inner.place(relx=0.5, rely=0.5, anchor="center")
                
                lbl = tk.Label(inner, image=img, bg="#444", cursor="hand2")
                lbl.pack()
                
                # BINDINGS
                for widget in (cell, inner, lbl):
                    widget.bind("<ButtonPress-1>", lambda e, p=i: self._on_drag_start(e, p))
                    widget.bind("<B1-Motion>", self._on_drag_motion)
                    widget.bind("<ButtonRelease-1>", self._on_drag_drop)
                
                tk.Label(inner, text=f"{i+1}", bg=self.colors['panel_bg'], fg="#999", font=("Arial", 9)).pack(pady=(2,0))
                self.thumbnail_widgets.append(cell)
                if i % 10 == 0: self.thumb_frame.update_idletasks()
            self._reflow_thumbnails()
        except Exception as e: print(f"Error: {e}")

    def _reflow_thumbnails(self):
        if not self.thumbnail_widgets: return
        panel_w = self.thumb_canvas.winfo_width()
        item_w = self.state["thumb_size"] + 30 
        cols = max(1, panel_w // item_w)
        self.state["grid_cols"] = cols
        for i in range(cols): self.thumb_frame.grid_columnconfigure(i, weight=1)
        for idx, widget in enumerate(self.thumbnail_widgets):
            widget.grid(row=idx // cols, column=idx % cols, sticky="n", padx=5, pady=5)

    def _on_sidebar_resize(self, event):
        item_w = self.state["thumb_size"] + 30
        new_cols = max(1, event.width // item_w)
        if new_cols != self.state["grid_cols"]: self._reflow_thumbnails()
        self.thumb_canvas.itemconfig(self.thumb_window_id, width=event.width)

    def _on_thumb_frame_configure(self, event):
        self.thumb_canvas.configure(scrollregion=self.thumb_canvas.bbox("all"))
    
    def _jump_to_page(self, idx):
        self.state["page_idx"] = idx
        self._render_current_page()

    # --- DRAG AND DROP ---
    def _create_drag_ghost(self, idx, event):
        if self.drag_data["ghost_window"]: self.drag_data["ghost_window"].destroy()
        img = self.thumbnail_images[idx]
        ghost = tk.Toplevel(self.root)
        ghost.overrideredirect(True)
        ghost.attributes("-alpha", 0.6)
        ghost.attributes("-topmost", True)
        lbl = tk.Label(ghost, image=img, bg="#333", bd=2, relief="solid")
        lbl.pack()
        self.drag_data["ghost_window"] = ghost
        ghost.geometry(f"+{event.x_root + 10}+{event.y_root + 10}")

    def _update_drop_indicator(self, target_idx, side="left"):
        if not self.drag_data["indicator"]:
            self.drag_data["indicator"] = tk.Frame(self.thumb_frame, bg="#00FFFF", width=4)
            self.drag_data["indicator_active"] = True
            self._animate_drop_indicator()
        ind = self.drag_data["indicator"]
        if target_idx is not None and 0 <= target_idx < len(self.thumbnail_widgets):
            tgt = self.thumbnail_widgets[target_idx]
            x, y, w, h = tgt.winfo_x(), tgt.winfo_y(), tgt.winfo_width(), tgt.winfo_height()
            px = x - 4 if side == "left" else (x + w)
            ind.place(x=px, y=y, height=h, width=4); ind.lift()
        else: ind.place_forget()

    def _animate_drop_indicator(self):
        if not self.drag_data["indicator_active"] or not self.drag_data["indicator"]: return
        try:
            cur = self.drag_data["indicator"].cget("bg")
            self.drag_data["indicator"].configure(bg="#FFFF00" if cur == "#00FFFF" else "#00FFFF")
            self.root.after(80, self._animate_drop_indicator)
        except: self.drag_data["indicator_active"] = False

    def _on_drag_start(self, event, idx):
        self._jump_to_page(idx)
        self.drag_data["source_idx"] = idx
        if 0 <= idx < len(self.thumbnail_widgets): self.thumbnail_widgets[idx].configure(bg="#007acc")
        self._create_drag_ghost(idx, event)

    def _on_drag_motion(self, event):
        if self.drag_data["ghost_window"]:
            self.drag_data["ghost_window"].geometry(f"+{event.x_root + 15}+{event.y_root + 15}")
        
        target = self.root.winfo_containing(*self.root.winfo_pointerxy())
        t_idx = self._get_thumbnail_index(target)
        
        if t_idx is not None:
            w = self.thumbnail_widgets[t_idx]
            side = "left" if (event.x_root - w.winfo_rootx()) < (w.winfo_width()/2) else "right"
            drop_idx = t_idx if side == "left" else t_idx + 1
            src = self.drag_data["source_idx"]
            
            if drop_idx in (src, src+1):
                if self.drag_data["indicator"]: self.drag_data["indicator"].place_forget()
                self.drag_data["drop_target_idx"] = None
            else:
                self._update_drop_indicator(t_idx, side)
                self.drag_data["drop_target_idx"] = drop_idx
        else:
            if self.drag_data["indicator"]: self.drag_data["indicator"].place_forget()
            self.drag_data["drop_target_idx"] = None

    def _on_drag_drop(self, event):
        src, final = self.drag_data["source_idx"], self.drag_data["drop_target_idx"]
        
        if self.drag_data["ghost_window"]: self.drag_data["ghost_window"].destroy()
        if self.drag_data["indicator"]: self.drag_data["indicator"].destroy(); self.drag_data["indicator"] = None
        
        if src is not None: self.thumbnail_widgets[src].configure(bg=self.colors['panel_bg'])
        
        if src is not None and final is not None:
            target_arg = final
            if final >= self.state["total_pages"]: target_arg = -1
            
            if self.engine.move_page(src, target_arg):
                self._regenerate_thumbnails()
                new_p = final if final <= src else final - 1
                if target_arg == -1: new_p = self.state["total_pages"] - 1
                self.state["page_idx"] = max(0, min(new_p, self.state["total_pages"]-1))
                self._render_current_page()
                
        self.drag_data["source_idx"] = None

    def _get_thumbnail_index(self, widget):
        curr = widget
        while curr:
            if curr in self.thumbnail_widgets: return self.thumbnail_widgets.index(curr)
            if curr in (self.thumb_frame, self.root): break
            curr = curr.master
        return None

    # --- LOADING (THINGY-MA-BOBBER STYLE) ---
    def _show_loading(self, message="Processing..."):
        if self.loading_overlay: return
        # Fullscreen overlay
        self.loading_overlay = tk.Frame(self.root, bg="black")
        self.loading_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        
        # Center container
        # Box matches the 'ThingyMaBobber' vibe: Dark background
        box = tk.Frame(self.loading_overlay, bg="#111", padx=30, pady=30, relief="flat")
        box.place(relx=0.5, rely=0.5, anchor="center")
        
        # Canvas
        self.spinner_canvas = tk.Canvas(box, width=120, height=120, bg="#111", highlightthickness=0)
        self.spinner_canvas.pack(pady=(0, 20))
        
        # Boot Log Label
        self.loading_label = tk.Label(box, text=message, bg="#111", fg="white", font=("Consolas", 12, "bold"))
        self.loading_label.pack()
        
        # Init State
        self.spinner_running = True
        self.spinner_state = { "a1": 0, "a2": 0, "a3": 0, "hue": 0 }
        self._animate_spinner()
        self.root.update()

    def _hide_loading(self):
        self.spinner_running = False
        if self.loading_overlay:
            self.loading_overlay.destroy()
            self.loading_overlay = None

    def _get_neon_color(self, offset=0):
        # Cycling hue
        h = (self.spinner_state["hue"] + offset) % 1.0
        r, g, b = colorsys.hsv_to_rgb(h, 1.0, 1.0)
        return f'#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}'

    def _draw_arc(self, cx, cy, r, width, start, extent, color):
        self.spinner_canvas.create_arc(
            cx-r, cy-r, cx+r, cy+r,
            start=start, extent=extent,
            outline=color, width=width, style="arc"
        )

    def _animate_spinner(self):
        if not self.spinner_running: return
        
        c = self.spinner_canvas
        c.delete("all")
        
        w, h = 120, 120
        cx, cy = w/2, h/2
        base = 50
        
        # Update State
        self.spinner_state["hue"] += 0.01
        if self.spinner_state["hue"] > 1: self.spinner_state["hue"] = 0
        
        # Colors
        c1 = self._get_neon_color(0.0)
        c2 = self._get_neon_color(0.33)
        c3 = self._get_neon_color(0.66)
        
        # Ring 1 (Inner, Fast)
        self.spinner_state["a1"] -= 8
        r1 = base * 0.5
        for i in range(3):
            self._draw_arc(cx, cy, r1, 4, self.spinner_state["a1"] + (i*120), 80, c1)
            
        # Ring 2 (Middle)
        self.spinner_state["a2"] += 5
        r2 = base * 0.75
        self._draw_arc(cx, cy, r2, 3, self.spinner_state["a2"], 160, c2)
        self._draw_arc(cx, cy, r2, 3, self.spinner_state["a2"]+180, 160, c2)
        
        # Ring 3 (Outer, Slow)
        self.spinner_state["a3"] -= 3
        r3 = base
        self._draw_arc(cx, cy, r3, 2, self.spinner_state["a3"], 300, c3)
        
        self.root.after(30, self._animate_spinner)

    def _run_async(self, target_func, on_complete, *args, message="Processing..."):
        def wrapper():
            result = target_func(*args)
            self.root.after(0, lambda: on_complete(result))
        
        self._show_loading(message)
        threading.Thread(target=wrapper, daemon=True).start()