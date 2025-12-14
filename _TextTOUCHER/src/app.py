#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
== Quick Text Generator ==

A Tkinter-based utility for quickly generating text files.
Now supports custom/no extensions via the "(None)" dropdown option.
"""

import sys
import os
import argparse
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk
from datetime import datetime

# ==========================================
#           USER CONFIGURATION
# ==========================================
# Customize your app startup defaults here:
CONFIG = {
    "WINDOW_WIDTH":  600,
    "WINDOW_HEIGHT": 600,
    "APP_TITLE":     "Quick Text Generator",
    "DEFAULT_EXT":   ".txt",
    "FONT_PATH":     ("Segoe UI", 9),       # Font for the path label
    "FONT_INPUT":    ("Consolas", 10),      # Font for the content editing
}
# ==========================================

class TextFileGenerator:
    """
    Main application logic for the Text File Generator.
    """
    def __init__(self, root):
        self.root = root
        self.root.title(CONFIG["APP_TITLE"])
        
        # Apply Configured Geometry
        geom_str = f"{CONFIG['WINDOW_WIDTH']}x{CONFIG['WINDOW_HEIGHT']}"
        self.root.geometry(geom_str)

        # --- Variables ---
        self.selected_folder_path = tk.StringVar(value="")
        self.use_timestamp = tk.BooleanVar(value=False)
        self.file_extension = tk.StringVar(value=CONFIG["DEFAULT_EXT"])

        # --- UI Layout ---
        self._build_ui()
        
        # UX Polish: Focus the filename entry immediately
        self.ent_filename.focus_set()

    def _build_ui(self):
        """Constructs the visual elements of the application."""
        
        # 1. Path Display (Top Bar)
        # We use a LabelFrame or just a Frame with a border to make it pop
        path_frame = tk.Frame(self.root, bg="#f0f0f0", pady=5, padx=10, relief="groove", bd=1)
        path_frame.pack(fill="x", side="top")

        tk.Label(path_frame, text="Save Path:", bg="#f0f0f0", fg="#666666").pack(side="left")
        
        self.lbl_path = tk.Label(
            path_frame, 
            text="No folder selected (Click 📂 below)", 
            fg="red", 
            bg="#f0f0f0",
            font=CONFIG["FONT_PATH"],
            anchor="w"
        )
        self.lbl_path.pack(side="left", fill="x", expand=True, padx=(5, 0))

        # 2. Main Controls Container
        # Holds the inputs and the content area
        main_body = tk.Frame(self.root, padx=15, pady=15)
        main_body.pack(fill="both", expand=True)

        # -- Row A: [Folder Btn] [Filename Input] [Extension] --
        input_row = tk.Frame(main_body)
        input_row.pack(fill="x", pady=(0, 10))

        # Folder Button (Square, Icon-like)
        # Using Unicode 📂 to keep it single-file without needing .png assets
        btn_folder = tk.Button(
            input_row, 
            text="📂", 
            font=("Arial", 12),
            width=3, 
            command=self.select_folder,
            cursor="hand2"
        )
        btn_folder.pack(side="left", padx=(0, 10))

        # Filename Entry
        tk.Label(input_row, text="Name:").pack(side="left")
        self.ent_filename = tk.Entry(input_row, font=("Segoe UI", 10))
        self.ent_filename.pack(side="left", fill="x", expand=True, padx=(5, 5))

        # Extension Dropdown
        extensions = [".txt", ".py", ".md", ".json", ".csv", ".log", ".bat", ".sh", ".yaml", " (None)"]
        self.combo_ext = ttk.Combobox(
            input_row, 
            values=extensions, 
            textvariable=self.file_extension, 
            width=8,
            state="readonly"
        )
        self.combo_ext.pack(side="right")

        # -- Row B: Content Area --
        tk.Label(main_body, text="File Content:").pack(anchor="w", pady=(5, 0))
        
        # Frame for text + scrollbar
        text_frame = tk.Frame(main_body)
        text_frame.pack(fill="both", expand=True, pady=(2, 10))

        scrollbar = tk.Scrollbar(text_frame)
        scrollbar.pack(side="right", fill="y")

        self.txt_content = tk.Text(
            text_frame, 
            font=CONFIG["FONT_INPUT"],
            undo=True, # Polish: Allow Ctrl+Z
            yscrollcommand=scrollbar.set
        )
        self.txt_content.pack(fill="both", expand=True)
        scrollbar.config(command=self.txt_content.yview)

        # -- Row C: Footer (Timestamp + Save) --
        footer_frame = tk.Frame(main_body)
        footer_frame.pack(fill="x")

        chk_timestamp = tk.Checkbutton(
            footer_frame, 
            text="Append Date/Time to filename", 
            variable=self.use_timestamp
        )
        chk_timestamp.pack(side="left")

        # Save Button
        self.btn_save = tk.Button(
            footer_frame, 
            text="SAVE FILE", 
            state="disabled", 
            bg="#dddddd", 
            font=("Segoe UI", 9, "bold"),
            command=self.save_file,
            cursor="arrow"
        )
        self.btn_save.pack(side="right", padx=(10, 0), ipadx=20)


    def select_folder(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.selected_folder_path.set(folder_selected)
            # Update path label color/text
            self.lbl_path.config(text=folder_selected, fg="#0055aa") # Professional Blue
            # Enable save button with a visual cue (Greenish tint if supported, or standard)
            self.btn_save.config(state="normal", bg="#e1e1e1", cursor="hand2") 
        else:
            if not self.selected_folder_path.get():
                self.lbl_path.config(text="No folder selected (Click 📂 below)", fg="red")
                self.btn_save.config(state="disabled", bg="#dddddd", cursor="arrow")

    def save_file(self):
        raw_name = self.ent_filename.get().strip()
        content = self.txt_content.get("1.0", tk.END)
        path = self.selected_folder_path.get()
        default_ext = self.file_extension.get()

        if not raw_name:
            messagebox.showwarning("Missing Data", "Please enter a file name.")
            self.ent_filename.focus_set()
            return

        # --- EXTENSION LOGIC ---
        if default_ext == " (None)":
            default_ext = ""

        base_name, user_ext = os.path.splitext(raw_name)
        final_ext = user_ext if user_ext else default_ext
        
        # --- TIMESTAMP LOGIC ---
        if self.use_timestamp.get():
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"{base_name}_{timestamp}{final_ext}"
        else:
            filename = f"{base_name}{final_ext}"

        full_path = os.path.join(path, filename)

        # --- OVERWRITE PROTECTION ---
        if os.path.exists(full_path):
            confirm = messagebox.askyesno(
                "Confirm Overwrite", 
                f"The file '{filename}' already exists.\n\nDo you want to overwrite it?"
            )
            if not confirm:
                return 

        try:
            # Using newline='' handles line endings better across OSs
            with open(full_path, "w", encoding="utf-8", newline='') as f:
                f.write(content)
            
            messagebox.showinfo("Success", f"File Saved:\n{full_path}")
            
            # Reset logic
            self.ent_filename.delete(0, tk.END)
            self.txt_content.delete("1.0", tk.END)
            self.ent_filename.focus_set() # Jump back to name for next file
            
        except Exception as e:
            messagebox.showerror("Error", f"Could not save file:\n{e}")

# 4. CLI ENTRY POINT
def main():
    parser = argparse.ArgumentParser(description="Launch the Quick Text Generator GUI.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print status.")
    args = parser.parse_args()

    if args.verbose:
        print("Initializing Quick Text Generator...", file=sys.stderr)

    try:
        root = tk.Tk()
        app = TextFileGenerator(root)
        root.mainloop()
        sys.exit(0)
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()