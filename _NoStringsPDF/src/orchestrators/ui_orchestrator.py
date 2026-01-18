"""
ORCHESTRATOR: UI Orchestrator
DESCRIPTION: Manages the layout, events, and dialogs of the main application.
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, Menu
import os
from src.microservices._TkinterButtonMS import TkinterButtonMS

class MainUIOrchestrator:
    def __init__(self, root, shell, theme_mgr, engine):
        self.root = root
        self.shell = shell
        self.theme_mgr = theme_mgr
        self.engine = engine
        self.colors = self.theme_mgr.get_theme()
        
        # State
        self.state = {
            "zoom": 1.0,
            "page_idx": 0,
            "total_pages": 0,
            "file_path": None,
            "thumb_size": 180,
            "grid_cols": 1
        }
        
        self.thumbnail_widgets = [] 
        self.thumbnail_images = []
        
        # Build UI
        self._build_layout()
        self._build_toolbar()
        self._build_context_menu()

    def _build_layout(self):
        container = self.shell.get_main_container()
        
        # Toolbar
        self.toolbar_frame = tk.Frame(container, bg=self.colors['panel_bg'], height=40)
        self.toolbar_frame.pack(side="top", fill="x", pady=(0, 2))
        
        # Splitter
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
        
        # Events
        self.thumb_frame.bind("<Configure>", self._on_thumb_frame_configure)
        self.thumb_canvas.bind("<Configure>", self._on_sidebar_resize)
        self.canvas.bind("<Button-3>", self._show_context_menu)
        self.root.bind_all("<MouseWheel>", self._dispatch_scroll)

    def _build_toolbar(self):
        def add_btn(text, cmd, side="left"):
            btn = TkinterButtonMS(self.toolbar_frame, text=text, command=cmd, theme=self.colors)
            btn.pack(side=side, padx=2, pady=4)
        
        add_btn("OPEN", self._action_open)
        # New Extract Button
        add_btn("EXTRACT/ORDER", self._show_extract_dialog)
        add_btn("EXPORT...", self._show_compression_dialog)
        
        tk.Frame(self.toolbar_frame, bg=self.colors['panel_bg'], width=20).pack(side="left")
        add_btn("ROT L", lambda: self._action_rotate(False)) 
        add_btn("ROT R", lambda: self._action_rotate(True))
        tk.Frame(self.toolbar_frame, bg=self.colors['panel_bg'], width=20).pack(side="left")
        add_btn("ZOOM -", lambda: self._change_main_zoom(-0.2))
        add_btn("ZOOM +", lambda: self._change_main_zoom(0.2))
        add_btn("NEXT >", self._next_page, side="right")
        add_btn("< PREV", self._prev_page, side="right")

    def _build_context_menu(self):
        self.context_menu = Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Rotate CW", command=lambda: self._action_rotate(True))
        self.context_menu.add_command(label="Rotate CCW", command=lambda: self._action_rotate(False))

    def _show_context_menu(self, event):
        self.context_menu.post(event.x_root, event.y_root)

    # --- DIALOG: EXTRACT / REORDER ---
    def _show_extract_dialog(self):
        if not self.state["file_path"]: 
            return messagebox.showwarning("No File", "Please open a PDF first.")
        
        dlg = tk.Toplevel(self.root)
        dlg.title("Extract & Reorder Pages")
        dlg.geometry("400x250")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.configure(bg="#2d2d2d")
        
        tk.Label(dlg, text="Extract / Reorder", bg="#2d2d2d", fg="white", font=("Arial", 12, "bold")).pack(pady=10)
        tk.Label(dlg, text=f"Document has {self.state['total_pages']} pages.", bg="#2d2d2d", fg="#aaa").pack()
        
        tk.Label(dlg, text="Enter Page Range (e.g. 1, 3, 5-10):", bg="#2d2d2d", fg="white", font=("Arial", 9)).pack(pady=(15, 5))
        
        # Input Box
        entry = tk.Entry(dlg, width=40, font=("Consolas", 11))
        entry.pack(pady=5)
        entry.focus()
        
        def do_extract():
            page_str = entry.get().strip()
            if not page_str: return
            
            path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF Files", "*.pdf")])
            if path:
                success, msg = self.engine.save_subset(path, page_str)
                if success:
                    messagebox.showinfo("Success", msg)
                    dlg.destroy()
                else:
                    messagebox.showerror("Error", msg)

        TkinterButtonMS(dlg, text="SAVE NEW FILE", command=do_extract, theme=self.colors).pack(fill="x", padx=40, pady=20)


    # --- DIALOG: COMPRESSION ---
    def _show_compression_dialog(self):
        if not self.state["file_path"]: 
            return messagebox.showwarning("No File", "Please open a PDF first.")

        dlg = tk.Toplevel(self.root)
        dlg.title("Advanced Export Options")
        dlg.geometry("400x550")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.configure(bg="#2d2d2d")

        style = {"bg": "#2d2d2d", "fg": "#eeeeee", "selectcolor": "#444", "activebackground": "#2d2d2d", "activeforeground": "#fff"}
        lbl_style = {"bg": "#2d2d2d", "fg": "#aaaaaa", "font": ("Arial", 9)}

        vars = {
            "optimize": tk.BooleanVar(value=True),
            "dpi": tk.IntVar(value=150),
            "quality": tk.IntVar(value=75),
            "grayscale": tk.BooleanVar(value=False),
            "flatten": tk.BooleanVar(value=True),
            "masks": tk.BooleanVar(value=False),
            "dedup": tk.BooleanVar(value=True),
            "stream": tk.BooleanVar(value=True)
        }

        tk.Label(dlg, text="Optimization Settings", bg="#2d2d2d", fg="white", font=("Arial", 12, "bold")).pack(pady=10)

        f_img = tk.LabelFrame(dlg, text="Images", bg="#2d2d2d", fg="white", padx=10, pady=10)
        f_img.pack(fill="x", padx=10, pady=5)

        tk.Checkbutton(f_img, text="Enable Image Optimization", variable=vars["optimize"], **style).pack(anchor="w")
        
        tk.Label(f_img, text="Target DPI (72=Screen, 150=Read, 300=Print)", **lbl_style).pack(anchor="w")
        tk.Scale(f_img, variable=vars["dpi"], from_=50, to=300, orient="horizontal", bg="#2d2d2d", fg="white", highlightthickness=0).pack(fill="x")

        tk.Label(f_img, text="JPEG Quality (1-100)", **lbl_style).pack(anchor="w")
        tk.Scale(f_img, variable=vars["quality"], from_=10, to=100, orient="horizontal", bg="#2d2d2d", fg="white", highlightthickness=0).pack(fill="x")

        tk.Checkbutton(f_img, text="Convert to Grayscale", variable=vars["grayscale"], **style).pack(anchor="w")
        tk.Checkbutton(f_img, text="Flatten Transparency (Fix Black Pages)", variable=vars["flatten"], **style).pack(anchor="w")
        tk.Checkbutton(f_img, text="Process Masks (Risky!)", variable=vars["masks"], **style).pack(anchor="w")

        f_str = tk.LabelFrame(dlg, text="Structure", bg="#2d2d2d", fg="white", padx=10, pady=10)
        f_str.pack(fill="x", padx=10, pady=5)

        tk.Checkbutton(f_str, text="Deduplicate Objects", variable=vars["dedup"], **style).pack(anchor="w")
        tk.Checkbutton(f_str, text="Compress Streams", variable=vars["stream"], **style).pack(anchor="w")

        def do_save():
            path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF Files", "*.pdf")])
            if path:
                settings = {
                    "optimize_images": vars["optimize"].get(),
                    "target_dpi": vars["dpi"].get(),
                    "jpeg_quality": vars["quality"].get(),
                    "grayscale": vars["grayscale"].get(),
                    "flatten_transparency": vars["flatten"].get(),
                    "process_masks": vars["masks"].get(),
                    "deduplicate": vars["dedup"].get(),
                    "compress_streams": vars["stream"].get()
                }
                dlg.destroy()
                self.root.update()
                success = self.engine.save_advanced(path, settings)
                if success:
                    messagebox.showinfo("Success", f"File saved to:\n{path}")
                else:
                    messagebox.showerror("Error", "Save failed.")

        TkinterButtonMS(dlg, text="SAVE FILE", command=do_save, theme=self.colors).pack(fill="x", padx=20, pady=20)

    # --- Actions ---
    def _action_open(self):
        path = filedialog.askopenfilename(filetypes=[("PDF Files", "*.pdf")])
        if path:
            self.state["total_pages"] = self.engine.load_pdf(path)
            self.state["file_path"] = path
            self.state["page_idx"] = 0
            self._render_current_page()
            self.root.after(100, self._regenerate_thumbnails)

    def _action_rotate(self, clockwise):
        if not self.state["file_path"]: return
        idx = self.state["page_idx"]
        self.engine.rotate_page(idx, clockwise)
        self._render_current_page()
        self._update_single_thumbnail(idx)

    # --- Helpers ---
    def _get_target_panel(self, widget):
        curr = widget
        while curr:
            if curr == self.left_container or curr == self.thumb_canvas or curr == self.thumb_frame: return "LEFT"
            if curr == self.right_panel or curr == self.canvas: return "RIGHT"
            if curr == self.root: break
            curr = curr.master
        return "UNKNOWN"

    def _dispatch_scroll(self, event):
        x, y = self.root.winfo_pointerxy()
        target = self.root.winfo_containing(x, y)
        if not target: return
        panel = self._get_target_panel(target)
        is_shift = (event.state & 0x0001) or (event.state & 0x0004)
        if panel == "LEFT":
            if is_shift: self._change_thumb_size(20 if event.delta > 0 else -20)
            else: self.thumb_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        elif panel == "RIGHT":
            if is_shift: self._change_main_zoom(0.2 if event.delta > 0 else -0.2)
            else: self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

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

    def _next_page(self):
        if self.state["page_idx"] < self.state["total_pages"] - 1:
            self.state["page_idx"] += 1
            self._render_current_page()

    def _prev_page(self):
        if self.state["page_idx"] > 0:
            self.state["page_idx"] -= 1
            self._render_current_page()

    def _render_current_page(self):
        if not self.state["file_path"]: return
        img, w, h = self.engine.render_page(self.state["page_idx"], self.state["zoom"])
        self.canvas.image = img 
        self.canvas.delete("all")
        self.canvas.create_image(w//2 + 20, h//2 + 20, image=img, anchor="center")
        self.canvas.configure(scrollregion=(0, 0, w+40, h+40))

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
                lbl = tk.Label(inner, image=img, bg="#444") 
                lbl.pack()
                tk.Label(inner, text=f"{i+1}", bg=self.colors['panel_bg'], fg="#999", font=("Arial", 9)).pack(pady=(2,0))
                lbl.bind("<Button-1>", lambda e, p=i: self._jump_to_page(p))
                self.thumbnail_widgets.append(cell)
                if i % 10 == 0: self.thumb_frame.update_idletasks()
            self._reflow_thumbnails()
        except Exception as e:
            print(f"Error generating thumbnails: {e}")

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