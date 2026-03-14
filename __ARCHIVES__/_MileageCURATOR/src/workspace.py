import os
import shutil
import tkinter as tk
from tkinter import filedialog
from pathlib import Path

WORKSPACES_DIR = Path("workspaces")

def pick_timeline_file():
    """Opens a native OS file dialog to select the Timeline.json file."""
    root = tk.Tk()
    root.withdraw()  # Hides the tiny blank Tkinter window
    root.attributes('-topmost', True) # Forces the dialog to the front
    
    file_path = filedialog.askopenfilename(
        title="Select your Google Timeline JSON",
        filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
    )
    root.destroy()
    return file_path

def create_new_project(project_name: str):
    """Creates a sandbox environment and copies the target JSON into it."""
    if not project_name.strip():
        print("Error: Project name cannot be empty.")
        return None

    # 1. Ask the user for the file
    print(f"Opening file picker for project '{project_name}'...")
    source_file = pick_timeline_file()
    
    if not source_file:
        print("File selection cancelled.")
        return None

    # 2. Build the sandbox directories
    WORKSPACES_DIR.mkdir(exist_ok=True)
    project_dir = WORKSPACES_DIR / project_name
    
    if project_dir.exists():
        print(f"Error: A project named '{project_name}' already exists.")
        return None
        
    project_dir.mkdir()
    
    # 3. Copy the massive file safely (shutil chunks it, so no RAM overflow)
    dest_file = project_dir / "Timeline.json"
    print(f"Copying JSON into sandbox (this might take a second for large files)...")
    shutil.copy2(source_file, dest_file)
    
    print(f"Success! Workspace created at: {project_dir}")
    return project_dir

if __name__ == "__main__":
    # Quick test: run this file directly to test the picker and folder creation
    name = input("Enter a new project name (e.g., 2025_Taxes): ")
    create_new_project(name)
