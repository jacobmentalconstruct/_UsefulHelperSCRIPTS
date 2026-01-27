"""
SERVICE_NAME: _ChalkBoardMS
ENTRY_POINT: _ChalkBoardMS.py
INTERNAL_DEPENDENCIES: base_service, microservice_std_lib
EXTERNAL_DEPENDENCIES: webview
"""
import json
import os
import webview
from microservice_std_lib import service_metadata, service_endpoint, BaseService
HTML_CONTENT = '\n<!DOCTYPE html>\n<html lang="en">\n<head>\n    <meta charset="UTF-8">\n    <title>OBS Signboard</title>\n    <link href="https://fonts.googleapis.com/css2?family=Neonderthaw&family=Press+Start+2P&family=Fredericka+the+Great&family=Orbitron:wght@700&family=Special+Elite&display=swap" rel="stylesheet">\n    <style>\n        body, html { margin: 0; padding: 0; height: 100%; overflow: hidden; display: flex; justify-content: center; align-items: center; transition: all 0.5s ease; }\n        #sign-container { width: 90%; text-align: center; outline: none; cursor: text; transition: transform 0.2s; }\n        \n        /* --- THEME 1: NEON NIGHTS --- */\n        body.neon { background-color: #050505; font-family: \'Neonderthaw\', cursive; }\n        body.neon #sign-container { color: #fff; font-size: 8rem; text-shadow: 0 0 7px #fff, 0 0 42px #bc13fe, 0 0 102px #bc13fe; animation: flicker 1.5s infinite alternate; }\n\n        /* --- THEME 2: 8-BIT HACKER --- */\n        body.terminal { background-color: #000; font-family: \'Press Start 2P\', cursive; }\n        body.terminal #sign-container { color: #00ff41; font-size: 3.5rem; text-shadow: 0 0 10px #00ff41; text-transform: uppercase; }\n        body.terminal #sign-container::after { content: \'_\'; animation: blink 1s step-end infinite; }\n\n        /* --- THEME 3: CHALKBOARD --- */\n        body.chalk { background-color: #2b3a28; font-family: \'Fredericka the Great\', cursive; background-image: radial-gradient(circle, rgba(255,255,255,0.05) 1px, transparent 1px); background-size: 20px 20px; }\n        body.chalk #sign-container { color: rgba(255,255,255,0.9); font-size: 6rem; transform: rotate(-1deg); }\n\n        /* --- NEW THEME 4: BLUEPRINT (Technical) --- */\n        body.blueprint { background-color: #003366; font-family: \'Orbitron\', sans-serif; background-image: linear-gradient(#004080 1px, transparent 1px), linear-gradient(90deg, #004080 1px, transparent 1px); background-size: 50px 50px; }\n        body.blueprint #sign-container { color: #00d9ff; font-size: 5rem; text-transform: uppercase; border: 2px solid #00d9ff; padding: 20px; box-shadow: 0 0 15px #00d9ff; }\n\n        /* --- NEW THEME 5: RETRO WOOD --- */\n        body.retro { background-color: #3d2b1f; font-family: \'Special Elite\', serif; background-image: repeating-linear-gradient(90deg, transparent, transparent 40px, rgba(0,0,0,0.1) 41px); }\n        body.retro #sign-container { color: #e6b450; font-size: 5.5rem; text-shadow: 2px 2px 0px #20150d; }\n\n        /* --- NEW THEME 6: CYBERPUNK (Yellow/Black) --- */\n        body.cyber { background-color: #fcee0a; font-family: \'Orbitron\', sans-serif; }\n        body.cyber #sign-container { color: #000; font-size: 5rem; font-weight: 900; text-transform: uppercase; font-style: italic; background: #000; color: #fcee0a; padding: 10px 40px; clip-path: polygon(0% 0%, 100% 0%, 95% 100%, 5% 100%); }\n\n        /* ANIMATIONS & EFFECTS */\n        @keyframes flicker { 0%, 19%, 21%, 100% { opacity: 1; } 20% { opacity: 0.5; } }\n        @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }\n        .shake { animation: shake 0.5s cubic-bezier(.36,.07,.19,.97) both; }\n        @keyframes shake { 10%, 90% { transform: translate3d(-1px, 0, 0); } 20%, 80% { transform: translate3d(2px, 0, 0); } 30%, 50%, 70% { transform: translate3d(-4px, 0, 0); } 40%, 60% { transform: translate3d(4px, 0, 0); } }\n    </style>\n</head>\n<body class="neon">\n    <div id="sign-container" contenteditable="true" spellcheck="false">ON AIR</div>\n\n    <script>\n        const container = document.getElementById(\'sign-container\');\n        \n        function updateDisplay(text, theme) {\n            container.innerText = text;\n            document.body.className = theme;\n        }\n\n        function triggerEffect(effect) {\n            if (effect === \'shake\') {\n                container.classList.add(\'shake\');\n                setTimeout(() => container.classList.remove(\'shake\'), 500);\n            }\n        }\n\n        // Notify Python on load\n        window.addEventListener(\'pywebviewready\', () => {\n            window.pywebview.api.loaded().then(state => {\n                updateDisplay(state.text, state.theme);\n            });\n        });\n\n        document.addEventListener(\'keydown\', (e) => {\n            const themes = { \'F1\': \'neon\', \'F2\': \'terminal\', \'F3\': \'chalk\', \'F4\': \'blueprint\', \'F5\': \'retro\', \'F6\': \'cyber\' };\n            if (themes[e.key]) {\n                document.body.className = themes[e.key];\n                window.pywebview.api.log_action(\'switch_theme_\' + themes[e.key]);\n            }\n        });\n    </script>\n</body>\n</html>\n'

@service_metadata(name='ChalkboardWeb', version='2.0.1', description='Integrated HTML5/CSS3 Digital Signage Engine', tags=['ui', 'webview', 'obs'], capabilities=['ui:gui'], side_effects=['ui:update'], internal_dependencies=['base_service', 'microservice_std_lib'], external_dependencies=['webview'])
class ChalkBoardMS(BaseService):

    def __init__(self):
        super().__init__('ChalkboardWeb')
        self._window = None
        self.state = {'text': 'ON AIR', 'theme': 'neon'}

    def loaded(self):
        """Called by JS when the page is ready."""
        print('Frontend handshake complete.')
        return self.state

    def log_action(self, action_name):
        """Called by JS when user interacts."""
        print(f'Webview Event: {action_name}')

    @service_endpoint(inputs={'text': 'str', 'theme': 'str'}, outputs={}, description='Updates the embedded HTML via JS injection.', tags=['ui', 'display'])
    def update_sign(self, text: str, theme: str='neon'):
        """Updates the embedded HTML via JS injection."""
        self.state['text'] = text
        self.state['theme'] = theme
        if self._window:
            sanitized_text = json.dumps(text)
            self._window.evaluate_js(f"updateDisplay({sanitized_text}, '{theme}')")

    @service_endpoint(inputs={'effect': 'str'}, outputs={}, description="Triggers CSS animations like 'shake'.", tags=['ui', 'animation'])
    def trigger_effect(self, effect: str):
        """Triggers CSS animations like 'shake'."""
        if self._window:
            self._window.evaluate_js(f"triggerEffect('{effect}')")
if __name__ == '__main__':
    api = ChalkBoardMS()
    print(f'Service Ready: {api}')
    window = webview.create_window('OBS Signboard v2', html=HTML_CONTENT, js_api=api, width=1000, height=700, background_color='#000000')
    api._window = window
    webview.start(debug=True)
