import importlib.util
import sys
import threading
import json
import logging
from typing import Any, Dict, Optional, Callable

# --- RUNTIME DEPENDENCY CHECK ---
# We check this early so the service fails gracefully if dependencies are missing.
REQUIRED = ["webview"] # 'pywebview' package import name is 'webview'
MISSING = []

if importlib.util.find_spec("webview") is None:
    MISSING.append("pywebview")

if MISSING:
    print('\n' + '!'*60)
    print(f'MISSING DEPENDENCIES for _MonacoHostMS:')
    print(f'Run:  pip install {" ".join(MISSING)}')
    print('!'*60 + '\n')
    # We don't exit here to allow the class to load, but launch() will likely fail.

import webview  # type: ignore
from microservice_std_lib import service_metadata, service_endpoint

logger = logging.getLogger("MonacoHost")

# ==============================================================================
# EMBEDDED HTML/JS
# ==============================================================================

MONACO_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Monaco Host</title>
    <style>
        html, body { margin: 0; padding: 0; width: 100%; height: 100%; overflow: hidden; background-color: #1e1e1e; font-family: sans-serif; }
        #container { display: flex; flex-direction: column; height: 100%; }
        #tabs { background: #252526; display: flex; overflow-x: auto; height: 35px; border-bottom: 1px solid #3e3e3e; }
        .tab { 
            padding: 8px 15px; color: #969696; background: #2d2d2d; cursor: pointer; border-right: 1px solid #1e1e1e; font-size: 12px;
            display: flex; align-items: center; white-space: nowrap;
        }
        .tab.active { background: #1e1e1e; color: #fff; border-top: 1px solid #007acc; }
        .tab:hover { background: #323233; color: #fff; }
        #editor { flex-grow: 1; }
    </style>
</head>
<body>
    <div id="container">
        <div id="tabs"></div>
        <div id="editor"></div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/monaco-editor@0.41.0/min/vs/loader.js"></script>
    <script>
        require.config({ paths: { 'vs': 'https://cdn.jsdelivr.net/npm/monaco-editor@0.41.0/min/vs' }});
        let editor;
        let models = {}; 
        let currentPath = null;

        require(['vs/editor/editor.main'], function() {
            editor = monaco.editor.create(document.getElementById('editor'), {
                value: "# Monaco Editor Ready\\n",
                language: 'python',
                theme: 'vs-dark',
                automaticLayout: true,
                fontSize: 14
            });

            if (window.pywebview) window.pywebview.api.signal_editor_ready();

            editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, function() {
                if (currentPath) {
                    window.pywebview.api.save_file(currentPath, editor.getValue());
                }
            });
        });

        window.pywebview = window.pywebview || {};
        window.pywebview.api = window.pywebview.api || {};

        window.pywebview.api.open_in_tab = function(filepath, content) {
            let ext = filepath.split('.').pop();
            let langMap = { 'py': 'python', 'js': 'javascript', 'html': 'html', 'json': 'json', 'css': 'css' };
            let lang = langMap[ext] || 'plaintext';

            if (!models[filepath]) {
                models[filepath] = monaco.editor.createModel(content, lang, monaco.Uri.file(filepath));
                const tab = document.createElement('div');
                tab.className = 'tab';
                tab.innerText = filepath.split(/[\\\\/]/).pop();
                tab.title = filepath;
                tab.onclick = () => switchTo(filepath);
                tab.dataset.path = filepath;
                document.getElementById('tabs').appendChild(tab);
            }
            switchTo(filepath);
        };

        window.pywebview.api.reveal_range = function(filepath, startLine, endLine) {
            if (filepath !== currentPath) switchTo(filepath);
            editor.revealLineInCenter(startLine);
            editor.setSelection({ startLineNumber: startLine, startColumn: 1, endLineNumber: endLine, endColumn: 1000 });
        };

        function switchTo(filepath) {
            if (!models[filepath]) return;
            editor.setModel(models[filepath]);
            currentPath = filepath;
            document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.path === filepath));
        }
    </script>
</body>
</html>
"""

# ==============================================================================
# HELPER CLASS (JS API Bridge)
# ==============================================================================

class MonacoApiBridge:
    """
    Acts as the bridge between Python and the JavaScript running inside the webview.
    Methods here are callable from JS via `window.pywebview.api.methodName()`.
    """
    def __init__(self):
        self._window = None
        self._ready_event = threading.Event()
        self.on_save_callback: Optional[Callable[[str, str], None]] = None

    def set_window(self, window):
        self._window = window

    def signal_editor_ready(self):
        """Called by JS when Monaco is fully loaded."""
        self._ready_event.set()
        logger.info("Monaco Editor reported ready.")

    def save_file(self, filepath: str, content: str):
        """Called by JS when Ctrl+S is pressed."""
        if self.on_save_callback:
            self.on_save_callback(filepath, content)
        else:
            logger.warning(f"Saved {filepath} (No callback registered)")

    def open_file_in_js(self, filepath: str, content: str):
        """Python helper to push data to JS."""
        self._ready_event.wait(timeout=10)
        if not self._window: 
            return
        # Using json.dumps ensures strings are properly escaped for JS
        js = f"window.pywebview.api.open_in_tab({json.dumps(filepath)}, {json.dumps(content)})"
        self._window.evaluate_js(js)


# ==============================================================================
# MICROSERVICE CLASS
# ==============================================================================

@service_metadata(
    name="MonacoHost",
    version="1.1.0",
    description="Hosts an embedded Monaco Editor instance using PyWebview.",
    tags=["ui", "editor", "webview"],
    capabilities=["ui:gui"]
)
class MonacoHostMS:
    """
    Hosts the Monaco Editor.
    This service spawns a GUI window and cannot be run in headless environments.
    """
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        # Instantiate the Bridge class, NOT this service class (avoids recursion/error)
        self.api = MonacoApiBridge()
        self.window = None

    @service_endpoint(
        inputs={"title": "str", "width": "int", "height": "int"},
        outputs={},
        description="Launches the editor window. Blocking call.",
        tags=["ui", "launch"],
        side_effects=["ui:window"]
    )
    def launch(self, title="Monaco Editor", width=1000, height=700, func=None):
        """
        Create and launch the window.
        :param func: Optional function to run in a separate thread after launch.
        """
        self.window = webview.create_window(
            title, 
            html=MONACO_HTML, 
            js_api=self.api,
            width=width, 
            height=height
        )
        self.api.set_window(self.window)
        
        # Start the GUI loop
        webview.start(func, debug=True) if func else webview.start(debug=True)

    def set_save_callback(self, callback: Callable[[str, str], None]):
        """Sets the function to trigger when Ctrl+S is pressed in the editor."""
        self.api.on_save_callback = callback

    def open_file(self, filepath: str, content: str):
        """Opens a file in the editor (must be called from a background thread or callback)."""
        self.api.open_file_in_js(filepath, content)


# --- Independent Test Block ---
if __name__ == "__main__":
    host = MonacoHostMS()
    
    def background_actions():
        # Wait for the JS to signal it's ready
        host.api._ready_event.wait()
        
        # Open a demo file
        print("Opening demo file...")
        host.open_file("demo.py", "print('Hello World')\n# Try Ctrl+S to save!")
        
        # Register what happens when user saves
        host.set_save_callback(lambda p, c: print(f"File: {p} was saved with {len(c)} chars."))

    print("Launching Monaco Host...")
    host.launch(func=background_actions)