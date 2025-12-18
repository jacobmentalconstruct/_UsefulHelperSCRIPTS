import webview
import threading
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Callable
from microservice_std_lib import service_metadata, service_endpoint

class MonacoBridge:
    """
    The Bridge: Handles bidirectional communication between Python and the Monaco Editor.
    """
    def __init__(self):
        self._window = None
        self._ready_event = threading.Event()
        self.on_save_callback: Optional[Callable[[str, str], None]] = None

    def set_window(self, window):
        self._window = window

    # --- JS -> Python (Called from Editor) ---
    
    def signal_editor_ready(self):
        """Called by JS when Monaco is fully loaded."""
        self._ready_event.set()
        print("Monaco Editor is ready.")

    def save_file(self, filepath: str, content: str):
        """Called by JS when Ctrl+S is pressed."""
        if self.on_save_callback:
            self.on_save_callback(filepath, content)
        else:
            print(f"Saved {filepath} (No callback registered)")

    def log(self, message: str):
        """Called by JS to print to Python console."""
        print(f"[Monaco JS]: {message}")

    # --- Python -> JS (Called from App) ---

    def open_file(self, filepath: str, content: str):
        """Opens a file in a new tab in the editor."""
        self._ready_event.wait(timeout=5)
        if not self._window: return
        
        safe_path = filepath.replace('\\', '\\\\').replace("'", "\\'")
        safe_content = json.dumps(content)
        
        js = f"window.pywebview.api.open_in_tab('{safe_path}', {safe_content})"
        self._window.evaluate_js(js)

    def highlight_range(self, filepath: str, start_line: int, end_line: int):
        """Scrolls to and highlights a specific line range."""
        self._ready_event.wait(timeout=5)
        if not self._window: return
        
        safe_path = filepath.replace('\\', '\\\\')
        js = f"window.pywebview.api.reveal_range('{safe_path}', {start_line}, {end_line})"
        self._window.evaluate_js(js)

@service_metadata(
name="MonacoHost",
version="1.0.0",
description="Hosts a Monaco Editor instance via PyWebView.",
tags=["ui", "editor", "webview"],
capabilities=["ui:gui", "filesystem:read"]
)
class MonacoHostMS:
    """
The Host: Manages the PyWebView window lifecycle.
"""
def __init__(self, config: Optional[Dict[str, Any]] = None):
self.config = config or {}
self.api = MonacoBridge()
default_html = str(Path(__file__).parent / "editor.html")
html_path = self.config.get("html_path", default_html)
self.html_path = Path(html_path).resolve()
self.window = None

    @service_endpoint(
    inputs={"title": "str", "width": "int", "height": "int", "func": "Callable"},
    outputs={},
    description="Launches the PyWebView editor window.",
    tags=["ui", "launch"],
    mode="sync",
    side_effects=["ui:gui"]
    )
    def launch(self, title="Monaco Editor", width=800, height=600, func=None):
    """
    Starts the editor window.
    :param func: Optional function to run in a background thread after launch.
    """
        self.window = webview.create_window(
            title, 
            str(self.html_path), 
            js_api=self.api,
            width=width, 
            height=height
        )
        self.api.set_window(self.window)
        
        if func:
            webview.start(func, debug=True)
        else:
            webview.start(debug=True)

# --- Independent Test Block ---
if __name__ == "__main__":
# 1. Setup
host = MonacoHostMS()
print("Service ready:", host)
    
    # 2. Define a background task to simulate "Opening a file" after 2 seconds
    def background_actions():
        import time
        print("Waiting for editor...")
        host.api._ready_event.wait()
        
        time.sleep(1)
        print("Opening test file...")
        
        dummy_code = """def hello_world():
    print("Hello from Python!")
    return True
"""
        host.api.open_file("test_script.py", dummy_code)
        
        # Define what happens on save
        host.api.on_save_callback = lambda path, content: print(f"SAVED TO DISK: {path}\nContent Size: {len(content)}")

# 3. Launch
print("Launching Editor...")
host.launch(func=background_actions)
