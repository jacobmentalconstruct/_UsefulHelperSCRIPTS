"""
PROJECT: _UsefulHelperSCRIPTS - Project Tidier
ROLE: Logic Orchestrator (The Brain)
"""
import threading
import requests
import logging
from typing import Dict, Any, List
from state import AppPhase

# Microservice Imports
from _ScannerMS import ScannerMS
from _SemanticChunkerMS import SemanticChunkerMS
from _DiffEngineMS import DiffEngineMS
from _CodeFormatterMS import CodeFormatterMS
from _CodeJanitorMS import CodeJanitorMS

OLLAMA_URL = "http://localhost:11434/api/generate"

class ProjectTidierBackend:
    def __init__(self, signal_bus, state, prompt_composer):
        self.bus = signal_bus
        self.state = state
        self.prompt_composer = prompt_composer
        self.logger = logging.getLogger("TidierBackend")
        self.review_gate = threading.Event()  # THE BARRIER 

        self.scanner = ScannerMS()
        self.chunker = SemanticChunkerMS()
        self.diff_engine = DiffEngineMS()
        self.formatter = CodeFormatterMS()
        self.janitor = CodeJanitorMS()
        
        self.current_model = "qwen2.5:1.5b"
        self.is_running = False
        self.pending_approval = None
        

    def _handle_user_decision(self, approved: bool):
        """Unblocks the engine after user input."""
        if approved and self.pending_approval:
            self._commit_hunk(self.pending_approval)

        self.pending_approval = None
        self.review_gate.set()  # OPEN THE GATE

    def _handle_start_request(self, data: Dict[str, Any]):
        """Entry point triggered by the UI 'Start' button via Signal Bus."""
        if self.is_running:
            return

        paths = data.get("paths", []) if isinstance(data, dict) else []
        if not paths:
            self.logger.warning("No paths selected for tidying.")
            return

        # Ensure the gate is open before starting a new run
        self.review_gate.set()

        # Run the heavy lifting in a background thread to keep UI responsive
        threading.Thread(target=self._run_engine, args=(paths,), daemon=True).start()

    def _update_model(self, data: Dict[str, Any]):
        """Update model selection when UI swaps models."""
        model = ""
        if isinstance(data, dict):
            model = str(data.get("model") or "").strip()
        else:
            model = str(data).strip()

        if model:
            self.current_model = model
            self.logger.info(f"Model updated: {self.current_model}")

    def _run_engine(self, paths: List[str]):
        self.is_running = True
        self.state.set_phase(AppPhase.INGESTING)
        self.logger.info("🚀 Tidy Session Started.")
        PROTECTED_DIRS = {'.venv', '__pycache__', '.git', 'node_modules'}

        for path in paths:
            if any(p in path for p in PROTECTED_DIRS): continue
            
            tree = self.scanner.scan_directory(path)
            files = self.scanner.flatten_tree(tree)
            
            for file_path in files:
                if any(p in file_path for p in PROTECTED_DIRS): continue
                self.logger.info(f"🔎 Scanning: {file_path}")
                
                content = open(file_path, 'r', encoding='utf-8', errors='ignore').read()
                chunks = self.chunker.chunk_file(content, file_path)
                
                for i, hunk in enumerate(chunks):
                    # Visual "Neural" Feedback
                    self.bus.emit("new_ai_thought", {
                        "file": file_path, "chunk_id": i, "content": hunk['content'],
                        "vector": [0.1] * 20, "color": "#007ACC" 
                    })
                    self.state.set_phase(AppPhase.THINKING)
                    self._process_hunk(file_path, hunk)

                            self.state.set_phase(AppPhase.DONE)
                            self.logger.info("🏁 Session Complete.")
                            self.is_running = False

    def _process_hunk(self, file_path, hunk):
        # Use the authoritative composer instead of hardcoded strings
        meta = {"file": file_path, "hunk_name": hunk.get('name')}
        prompt = self.prompt_composer.compose(hunk['content'], meta)
        try:
            res = requests.post(OLLAMA_URL, json={"model": self.current_model, "prompt": prompt, "stream": False}, timeout=30)
            cleaned = res.json().get("response", "").strip()

            if cleaned and cleaned != hunk['content']:
                self.logger.warning(f"⚠️ Clutter detected in {hunk['name']}. Pausing...")
                self.pending_approval = {"file": file_path, "before": hunk['content'], "after": cleaned, "hunk_name": hunk['name']}
                
                self.state.set_phase(AppPhase.REVIEWING)
                self.state.pending_review = self.pending_approval
                
                self.review_gate.clear() # CLOSE THE GATE 
                self.bus.emit("hunk_ready_for_review", self.pending_approval)
                self.review_gate.wait() # BLOCK UNTIL UI RESPONDS 
        except Exception as e:
            # Never allow the worker thread to deadlock on a closed gate.
            self.logger.error(f"AI Error: {e}")
            self.pending_approval = None
            self.state.set_phase(AppPhase.ERROR)
            self.bus.emit("engine_error", {"msg": str(e)})
            try:
                self.review_gate.set()  # FAIL-OPEN
            except Exception:
                pass

    def _commit_hunk(self, data):
        fmt = self.formatter.normalize_code(data['after'])
        self.diff_engine.update_file(data['file'], fmt['normalized'], author="TidierAI")
        self.bus.emit("commit_success", data['file'])









