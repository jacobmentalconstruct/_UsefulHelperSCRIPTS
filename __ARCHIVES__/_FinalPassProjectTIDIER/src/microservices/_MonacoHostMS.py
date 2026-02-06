import importlib.util
import sys
import threading
import json
import logging
from typing import Any, Dict, Optional, Callable
REQUIRED = ['webview']
MISSING = []
if importlib.util.find_spec('webview') is None:
    MISSING.append('pywebview')
if MISSING:
    print('\n' + '!' * 60)
    print(f'MISSING DEPENDENCIES for _MonacoHostMS:')
    print(f"Run:  pip install {' '.join(MISSING)}")
    print('!' * 60 + '\n')
import webview
from microservice_std_lib import service_metadata, service_endpoint
logger = logging.getLogger('MonacoHost')
MONACO_HTML = '\n<!DOCTYPE html>\n<html>\n<head>\n    <meta charset="UTF-8">\n    <title>Monaco Host</title>\n    <style>\n        html, body { margin: 0; padding: 0; width: 100%; height: 100%; overflow: hidden; background-color: #1e1e1e; font-family: sans-serif; }\n        #container { display: flex; flex-direction: column; height: 100%; }\n        #tabs { background: #252526; display: flex; overflow-x: auto; height: 35px; border-bottom: 1px solid #3e3e3e; }\n        .tab { \n            padding: 8px 15px; color: #969696; background: #2d2d2d; cursor: pointer; border-right: 1px solid #1e1e1e; font-size: 12px;\n            display: flex; align-items: center; white-space: nowrap;\n        }\n        .tab.active { background: #1e1e1e; color: #fff; border-top: 1px solid #007acc; }\n        .tab:hover { background: #323233; color: #fff; }\n        #editor { flex-grow: 1; }\n    </style>\n</head>\n<body>\n    <div id="container">\n        <div id="tabs"></div>\n        <div id="editor"></div>\n    </div>\n    <script src="https://cdn.jsdelivr.net/npm/monaco-editor@0.41.0/min/vs/loader.js"></script>\n    <script>\n        require.config({ paths: { \'vs\': \'https://cdn.jsdelivr.net/npm/monaco-editor@0.41.0/min/vs\' }});\n        let editor;\n        let models = {}; \n        let currentPath = null;\n\n        require([\'vs/editor/editor.main\'], function() {\n            editor = monaco.editor.create(document.getElementById(\'editor\'), {\n                value: "# Monaco Editor Ready\\n",\n                language: \'python\',\n                theme: \'vs-dark\',\n                automaticLayout: true,\n                fontSize: 14\n            });\n\n            if (window.pywebview) window.pywebview.api.signal_editor_ready();\n\n            editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, function() {\n                if (currentPath) {\n                    window.pywebview.api.save_file(currentPath, editor.getValue());\n                }\n            });\n        });\n\n        window.pywebview = window.pywebview || {};\n        window.pywebview.api = window.pywebview.api || {};\n\n        window.pywebview.api.open_in_tab = function(filepath, content) {\n            let ext = filepath.split(\'.\').pop();\n            let langMap = { \'py\': \'python\', \'js\': \'javascript\', \'html\': \'html\', \'json\': \'json\', \'css\': \'css\' };\n            let lang = langMap[ext] || \'plaintext\';\n\n            if (!models[filepath]) {\n                models[filepath] = monaco.editor.createModel(content, lang, monaco.Uri.file(filepath));\n                const tab = document.createElement(\'div\');\n                tab.className = \'tab\';\n                tab.innerText = filepath.split(/[\\\\/]/).pop();\n                tab.title = filepath;\n                tab.onclick = () => switchTo(filepath);\n                tab.dataset.path = filepath;\n                document.getElementById(\'tabs\').appendChild(tab);\n            }\n            switchTo(filepath);\n        };\n\n        window.pywebview.api.reveal_range = function(filepath, startLine, endLine) {\n            if (filepath !== currentPath) switchTo(filepath);\n            editor.revealLineInCenter(startLine);\n            editor.setSelection({ startLineNumber: startLine, startColumn: 1, endLineNumber: endLine, endColumn: 1000 });\n        };\n\n        function switchTo(filepath) {\n            if (!models[filepath]) return;\n            editor.setModel(models[filepath]);\n            currentPath = filepath;\n            document.querySelectorAll(\'.tab\').forEach(t => t.classList.toggle(\'active\', t.dataset.path === filepath));\n        }\n    </script>\n</body>\n</html>\n'

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
        logger.info('Monaco Editor reported ready.')

    def save_file(self, filepath: str, content: str):
        """Called by JS when Ctrl+S is pressed."""
        if self.on_save_callback:
            self.on_save_callback(filepath, content)
        else:
            logger.warning(f'Saved {filepath} (No callback registered)')

    def open_file_in_js(self, filepath: str, content: str):
        """Python helper to push data to JS."""
        self._ready_event.wait(timeout=10)
        if not self._window:
            return
        js = f'window.pywebview.api.open_in_tab({json.dumps(filepath)}, {json.dumps(content)})'
        self._window.evaluate_js(js)

@service_metadata(name='MonacoHost', version='1.1.0', description='Hosts an embedded Monaco Editor instance using PyWebview.', tags=['ui', 'editor', 'webview'], capabilities=['ui:gui'], internal_dependencies=['microservice_std_lib'], external_dependencies=['webview'])
class MonacoHostMS:
    """
    Hosts the Monaco Editor.
    This service spawns a GUI window and cannot be run in headless environments.
    """

    def __init__(self, config: Optional[Dict[str, Any]]=None):
        self.config = config or {}
        self.api = MonacoApiBridge()
        self.window = None

    @service_endpoint(inputs={'title': 'str', 'width': 'int', 'height': 'int'}, outputs={}, description='Launches the editor window. Blocking call.', tags=['ui', 'launch'], side_effects=['ui:window'])
    def launch(self, title='Monaco Editor', width=1000, height=700, func=None):
        """
        Create and launch the window.
        :param func: Optional function to run in a separate thread after launch.
        """
        self.window = webview.create_window(title, html=MONACO_HTML, js_api=self.api, width=width, height=height)
        self.api.set_window(self.window)
        webview.start(func, debug=True) if func else webview.start(debug=True)

    def set_save_callback(self, callback: Callable[[str, str], None]):
        """Sets the function to trigger when Ctrl+S is pressed in the editor."""
        self.api.on_save_callback = callback

    def open_file(self, filepath: str, content: str):
        """Opens a file in the editor (must be called from a background thread or callback)."""
        self.api.open_file_in_js(filepath, content)
if __name__ == '__main__':
    host = MonacoHostMS()

    def background_actions():
        host.api._ready_event.wait()
        print('Opening demo file...')
        host.open_file('demo.py', "print('Hello World')\n# Try Ctrl+S to save!")
        host.set_save_callback(lambda p, c: print(f'File: {p} was saved with {len(c)} chars.'))
    print('Launching Monaco Host...')
    host.launch(func=background_actions)
