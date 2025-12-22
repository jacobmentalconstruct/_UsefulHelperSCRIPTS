"""
SERVICE_NAME: _ChalkBoardMS
ENTRY_POINT: __ChalkBoardMS.py
DEPENDENCIES: None
"""

import json
import os
import webview

from microservice_std_lib import service_metadata, service_endpoint, BaseService

# ==============================================================================
# CONFIGURATION & ASSETS
# ==============================================================================
HTML_CONTENT = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>OBS Signboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Neonderthaw&family=Press+Start+2P&family=Fredericka+the+Great&family=Orbitron:wght@700&family=Special+Elite&display=swap" rel="stylesheet">
    <style>
        body, html { margin: 0; padding: 0; height: 100%; overflow: hidden; display: flex; justify-content: center; align-items: center; transition: all 0.5s ease; }
        #sign-container { width: 90%; text-align: center; outline: none; cursor: text; transition: transform 0.2s; }
        
        /* --- THEME 1: NEON NIGHTS --- */
        body.neon { background-color: #050505; font-family: 'Neonderthaw', cursive; }
        body.neon #sign-container { color: #fff; font-size: 8rem; text-shadow: 0 0 7px #fff, 0 0 42px #bc13fe, 0 0 102px #bc13fe; animation: flicker 1.5s infinite alternate; }

        /* --- THEME 2: 8-BIT HACKER --- */
        body.terminal { background-color: #000; font-family: 'Press Start 2P', cursive; }
        body.terminal #sign-container { color: #00ff41; font-size: 3.5rem; text-shadow: 0 0 10px #00ff41; text-transform: uppercase; }
        body.terminal #sign-container::after { content: '_'; animation: blink 1s step-end infinite; }

        /* --- THEME 3: CHALKBOARD --- */
        body.chalk { background-color: #2b3a28; font-family: 'Fredericka the Great', cursive; background-image: radial-gradient(circle, rgba(255,255,255,0.05) 1px, transparent 1px); background-size: 20px 20px; }
        body.chalk #sign-container { color: rgba(255,255,255,0.9); font-size: 6rem; transform: rotate(-1deg); }

        /* --- NEW THEME 4: BLUEPRINT (Technical) --- */
        body.blueprint { background-color: #003366; font-family: 'Orbitron', sans-serif; background-image: linear-gradient(#004080 1px, transparent 1px), linear-gradient(90deg, #004080 1px, transparent 1px); background-size: 50px 50px; }
        body.blueprint #sign-container { color: #00d9ff; font-size: 5rem; text-transform: uppercase; border: 2px solid #00d9ff; padding: 20px; box-shadow: 0 0 15px #00d9ff; }

        /* --- NEW THEME 5: RETRO WOOD --- */
        body.retro { background-color: #3d2b1f; font-family: 'Special Elite', serif; background-image: repeating-linear-gradient(90deg, transparent, transparent 40px, rgba(0,0,0,0.1) 41px); }
        body.retro #sign-container { color: #e6b450; font-size: 5.5rem; text-shadow: 2px 2px 0px #20150d; }

        /* --- NEW THEME 6: CYBERPUNK (Yellow/Black) --- */
        body.cyber { background-color: #fcee0a; font-family: 'Orbitron', sans-serif; }
        body.cyber #sign-container { color: #000; font-size: 5rem; font-weight: 900; text-transform: uppercase; font-style: italic; background: #000; color: #fcee0a; padding: 10px 40px; clip-path: polygon(0% 0%, 100% 0%, 95% 100%, 5% 100%); }

        /* ANIMATIONS & EFFECTS */
        @keyframes flicker { 0%, 19%, 21%, 100% { opacity: 1; } 20% { opacity: 0.5; } }
        @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }
        .shake { animation: shake 0.5s cubic-bezier(.36,.07,.19,.97) both; }
        @keyframes shake { 10%, 90% { transform: translate3d(-1px, 0, 0); } 20%, 80% { transform: translate3d(2px, 0, 0); } 30%, 50%, 70% { transform: translate3d(-4px, 0, 0); } 40%, 60% { transform: translate3d(4px, 0, 0); } }
    </style>
</head>
<body class="neon">
    <div id="sign-container" contenteditable="true" spellcheck="false">ON AIR</div>

    <script>
        const container = document.getElementById('sign-container');
        
        function updateDisplay(text, theme) {
            container.innerText = text;
            document.body.className = theme;
        }

        function triggerEffect(effect) {
            if (effect === 'shake') {
                container.classList.add('shake');
                setTimeout(() => container.classList.remove('shake'), 500);
            }
        }

        // Notify Python on load
        window.addEventListener('pywebviewready', () => {
            window.pywebview.api.loaded().then(state => {
                updateDisplay(state.text, state.theme);
            });
        });

        document.addEventListener('keydown', (e) => {
            const themes = { 'F1': 'neon', 'F2': 'terminal', 'F3': 'chalk', 'F4': 'blueprint', 'F5': 'retro', 'F6': 'cyber' };
            if (themes[e.key]) {
                document.body.className = themes[e.key];
                window.pywebview.api.log_action('switch_theme_' + themes[e.key]);
            }
        });
    </script>
</body>
</html>
"""

# ==============================================================================
# SERVICE DEFINITION
# ==============================================================================
@service_metadata(
    name="ChalkboardWeb",
    version="2.0.1",
    description="Integrated HTML5/CSS3 Digital Signage Engine",
    tags=["ui", "webview", "obs"],
    capabilities=["ui:gui"],
    dependencies=["webview", "json"],
    side_effects=["ui:update"]
)
class ChalkBoardMS(BaseService):
    def __init__(self):
        super().__init__("ChalkboardWeb")
        self._window = None
        self.state = {"text": "ON AIR", "theme": "neon"}

    # --- Internal/JS Callbacks ---
    def loaded(self):
        """Called by JS when the page is ready."""
        print("Frontend handshake complete.")
        return self.state

    def log_action(self, action_name):
        """Called by JS when user interacts."""
        print(f"Webview Event: {action_name}")

    # --- Public Endpoints ---
    @service_endpoint(
        inputs={"text": "str", "theme": "str"}, 
        outputs={},
        description="Updates the embedded HTML via JS injection.",
        tags=["ui", "display"]
    )
    def update_sign(self, text: str, theme: str = "neon"):
        """Updates the embedded HTML via JS injection."""
        self.state["text"] = text
        self.state["theme"] = theme
        if self._window:
            sanitized_text = json.dumps(text)
            self._window.evaluate_js(f"updateDisplay({sanitized_text}, '{theme}')")

    @service_endpoint(
        inputs={"effect": "str"}, 
        outputs={},
        description="Triggers CSS animations like 'shake'.",
        tags=["ui", "animation"]
    )
    def trigger_effect(self, effect: str):
        """Triggers CSS animations like 'shake'."""
        if self._window:
            self._window.evaluate_js(f"triggerEffect('{effect}')")

# ==============================================================================
# SELF-TEST / RUNNER
# ==============================================================================
if __name__ == "__main__":
    api = ChalkBoardMS()
    print(f"Service Ready: {api}")
    
    window = webview.create_window(
        'OBS Signboard v2', 
        html=HTML_CONTENT,
        js_api=api,
        width=1000, 
        height=700,
        background_color='#000000'
    )
    api._window = window
    webview.start(debug=True)