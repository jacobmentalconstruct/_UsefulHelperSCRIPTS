import webview # pip install pywebview
import threading
import time
import json
from typing import Optional, Dict, Any

# Mocking your microservice lib if missing
try:
    from microservice_std_lib import service_metadata, service_endpoint
except ImportError:
    def service_metadata(**kwargs): return lambda c: c
    def service_endpoint(**kwargs): return lambda f: f

@service_metadata(
    name="ChalkboardWeb",
    version="2.0.0",
    description="HTML5/CSS3 powered Digital Signage",
    tags=["ui", "webview", "obs"],
    capabilities=["ui:gui"]
)
class ChalkboardAPI:
    def __init__(self):
        self._window = None
        self.state = {"text": "ON AIR", "theme": "neon"}

    # --- JAVASCRIPT CALLS THIS ---
    def loaded(self):
        """Called by JS when the page is ready."""
        print("Frontend loaded!")
        return self.state

    def log_action(self, action_name):
        """Called by JS when a button is clicked."""
        print(f"User triggered: {action_name}")
        # Here you could trigger external hardware, lights, etc.

    # --- PYTHON CALLS THIS (Your Agent) ---
    @service_endpoint(inputs={"text": "str", "theme": "str"}, outputs={})
    def update_sign(self, text: str, theme: str = "neon"):
        """Updates the HTML via JavaScript injection."""
        self.state["text"] = text
        self.state["theme"] = theme
        
        if self._window:
            # Execute JS directly from Python!
            sanitized_text = json.dumps(text) # Safety
            self._window.evaluate_js(f"updateDisplay({sanitized_text}, '{theme}')")

    @service_endpoint(inputs={"effect": "str"}, outputs={})
    def trigger_effect(self, effect: str):
        """Triggers a CSS animation (boom, pow, etc)."""
        if self._window:
            self._window.evaluate_js(f"triggerEffect('{effect}')")

def start_app():
    api = ChalkboardAPI()
    
    # Load your HTML file directly
    window = webview.create_window(
        'OBS Rad-IO Signboard', 
        url='_ChalkBOARD.html', # Your HTML file path
        js_api=api, # Expose the class to JS
        width=900, 
        height=600,
        background_color='#000000'
    )
    api._window = window
    webview.start(debug=True) # debug=True lets you inspect element with right click

if __name__ == "__main__":
    start_app()