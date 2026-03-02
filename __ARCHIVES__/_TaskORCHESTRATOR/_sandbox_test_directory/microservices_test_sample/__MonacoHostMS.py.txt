"""
SERVICE_NAME: _MonacoHostMS
ENTRY_POINT: __MonacoHostMS.py
DEPENDENCIES: pywebview
"""

# --- RUNTIME DEPENDENCY CHECK ---
import importlib.util, sys
REQUIRED = ["pywebview"]
MISSING = []
for lib in REQUIRED:
    # Clean version numbers for check (e.g., pygame==2.0 -> pygame)
    clean_lib = lib.split('>=')[0].split('==')[0].split('>')[0].replace('-', '_')
    if importlib.util.find_spec(clean_lib) is None:
        if clean_lib == 'pywebview': clean_lib = 'webview' # Common alias
        if importlib.util.find_spec(clean_lib) is None:
            MISSING.append(lib)

if MISSING:
    print('\n' + '!'*60)
    print(f'MISSING DEPENDENCIES for _MonacoHostMS:')
    print(f'Run:  pip install {" ".join(MISSING)}')
    print('!'*60 + '\n')
    # sys.exit(1) # Uncomment to force stop if missing

import webview
import threading
import json
from pathlib import Path
from typing import Any, Dict, Optional, Callable
from microservice_std_lib import service_metadata, service_endpoint

# --- EMBEDDED MONACO HTML ---
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

class MonacoHostMS:
    def __init__(self):
        self._window = None
        self._ready_event = threading.Event()
        self.on_save_callback: Optional[Callable[[str, str], None]] = None

    def set_window(self, window):
        self._window = window

    def signal_editor_ready(self):
        self._ready_event.set()
        print("Monaco Editor is ready.")

    def save_file(self, filepath: str, content: str):
        if self.on_save_callback:
            self.on_save_callback(filepath, content)
        else:
            print(f"Saved {filepath} (No callback registered)")

    def open_file(self, filepath: str, content: str):
        self._ready_event.wait(timeout=10)
        if not self._window: return
        # Using json.dumps for both handles escaping perfectly
        js = f"window.pywebview.api.open_in_tab({json.dumps(filepath)}, {json.dumps(content)})"
        self._window.evaluate_js(js)

@service_metadata(
    name="MonacoHost",
    version="1.1.0",
    description="Hosts an embedded Monaco Editor instance.",
    tags=["ui", "editor", "webview"],
    capabilities=["ui:gui"]
)
class MonacoHostMS:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.api = MonacoHostMS()
        self.window = None

    @service_endpoint(mode="sync")
    def launch(self, title="Monaco Editor", width=1000, height=700, func=None):
        self.window = webview.create_window(
            title, 
            html=MONACO_HTML, # Pass the string directly here
            js_api=self.api,
            width=width, 
            height=height
        )
        self.api.set_window(self.window)
        webview.start(func, debug=True) if func else webview.start(debug=True)

if __name__ == "__main__":
    host = MonacoHostMS()
    
    def background_actions():
        host.api._ready_event.wait()
        host.api.open_file("demo.py", "print('Hello World')\\n# Try Ctrl+S")
        host.api.on_save_callback = lambda p, c: print(f"File: {p} was saved with {len(c)} chars.")

    host.launch(func=background_actions)