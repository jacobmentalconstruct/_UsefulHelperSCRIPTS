import json
import threading
import requests
import queue
from pathlib import Path

OLLAMA_URL = "http://localhost:11434/api/chat"

class CortexKernel:
    def __init__(self, registry_data, library_root):
        self.registry = registry_data
        self.root = library_root
        self.model = "qwen2.5-coder:latest" # Default

    def process_query(self, user_query, selected_files, callback):
        """
        The Master Orchestrator.
        Decides: Do I look at the Registry? Or the Code?
        """
        
        # STRATEGY 1: USER SELECTED SPECIFIC FILES
        # If the user manually selected files, they want to talk about those.
        if selected_files:
            self._run_code_analysis(user_query, selected_files, callback)
            return

        # STRATEGY 2: GLOBAL QUERY (No selection)
        # If no files selected, we assume they are asking about the Library/Registry.
        # We perform a "Registry Lookup" first.
        self._run_registry_lookup(user_query, callback)

    def _run_registry_lookup(self, query, callback):
        """
        Fast path: Uses registry.json metadata only. 
        Zero hallucination risk because we don't feed it code to get confused by.
        """
        # Create a clean, text-based list for the LLM
        inventory = []
        for s in self.registry:
            # Truncate description to save tokens and focus on the name
            desc = s.get('description', 'No description').replace('\n', ' ')[:150]
            inventory.append(f"SERVICE: {s['name']}\nSUMMARY: {desc}")
        
        context_str = "\n---\n".join(inventory)

        system_prompt = (
            "You are the Library Librarian. You have a list of available microservices metadata.\n"
            "1. Answer ONLY based on the list below.\n"
            "2. If asked to list services, format them cleanly.\n"
            "3. Do not invent services."
        )

        self._call_ollama(system_prompt, f"DATA:\n{context_str}\n\nQUERY: {query}", callback)

    def _run_code_analysis(self, query, files, callback):
        """
        Deep path: Reads actual source code.
        """
        # If too many files (e.g., > 5), we warn the user or summarize first.
        if len(files) > 10:
            callback("⚠️ SYSTEM WARNING: You selected " + str(len(files)) + " files.\n"
                     "Sending this much code will confuse the model. Please select fewer files or use the Registry.")
            return

        context_str = ""
        for name, content in files.items():
            context_str += f"\n=== FILE: {name} ===\n{content}\n"

        system_prompt = "You are a generic Coding Assistant. Answer based on the code provided."
        self._call_ollama(system_prompt, f"CODE:\n{context_str}\n\nQUERY: {query}", callback)

    def _call_ollama(self, system, user, callback):
        def worker():
            try:
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user}
                    ],
                    "stream": False,
                    "options": {"temperature": 0.1}
                }
                resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
                if resp.status_code == 200:
                    callback(resp.json()['message']['content'])
                else:
                    callback(f"Error: {resp.status_code}")
            except Exception as e:
                callback(f"Connection Error: {e}")
        
        threading.Thread(target=worker, daemon=True).start()