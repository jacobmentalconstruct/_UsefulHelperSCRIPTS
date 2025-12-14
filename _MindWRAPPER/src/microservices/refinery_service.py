import json
from typing import Dict, Any, Optional
from .base_service import BaseService
from .cartridge_service import CartridgeService
from .neural_service import NeuralService

class RefineryService(BaseService):
    """
    The Night Shift.
    Processes 'RAW' files from the Cartridge, extracts metadata,
    and promotes them to 'ENRICHED'.
    """

    def __init__(self, cartridge: CartridgeService, neural: NeuralService):
        super().__init__("RefineryService")
        self.cartridge = cartridge
        self.neural = neural
        self.is_running = False

    def process_pending_files(self, batch_size: int = 10) -> int:
        """
        Fetches a batch of RAW files and runs the appropriate handler.
        Returns number of files processed.
        """
        pending = self.cartridge.get_pending_files(limit=batch_size)
        if not pending:
            return 0

        self.log_info(f"Refinery spinning up for {len(pending)} files...")
        
        # We can parallelize this using NeuralService's helper
        results = self.neural.process_parallel(pending, self._process_single_file)
        
        return len(results)

    def _process_single_file(self, file_row: Dict) -> bool:
        """
        Worker function. Determines type and enriches.
        """
        file_id = file_row["id"]
        path = file_row["path"]
        mime = file_row["mime_type"]
        content = file_row["content"]

        meta = {}
        status = "ENRICHED"

        try:
            # --- PLUGIN DISPATCHER ---
            if path.endswith(".py"):
                meta = self._handle_python(content)
            elif path.endswith(".md") or path.endswith(".txt"):
                meta = self._handle_generic_text(content)
            elif not content:
                # It's a binary blob we don't have a handler for yet
                meta = {"type": "binary", "info": "No handler loaded"}
                status = "SKIPPED_BINARY"
            else:
                meta = self._handle_generic_text(content)

            # Update DB
            self.cartridge.update_file_status(file_id, status, metadata=meta)
            return True

        except Exception as e:
            self.log_error(f"Failed to refine {path}: {e}")
            self.cartridge.update_file_status(file_id, "ERROR", metadata={"error": str(e)})
            return False

    # --- HANDLERS (The "Plugins") ---

    def _handle_python(self, content: str) -> Dict:
        """Uses 1.5b-coder to extract structure."""
        prompt = f"""
        Analyze this Python code. Return a JSON object with:
        - "classes": [list of class names]
        - "functions": [list of function names]
        - "imports": [list of imports]
        - "complexity": (Low/Medium/High)
        - "summary": "One sentence description"
        
        Code:
        {content[:3000]}
        """
        # Tier='fast' uses the CPU-bound 1.5b-coder
        response = self.neural.request_inference(prompt, tier="fast", format_json=True)
        try:
            return json.loads(response)
        except:
            return {"summary": "Analysis failed", "raw_inference": response[:100]}

    def _handle_generic_text(self, content: str) -> Dict:
        """Uses 3b-cpu for general summaries."""
        prompt = f"""
        Summarize this text in one sentence. Return JSON with key 'summary'.
        Text:
        {content[:2000]}
        """
        # Tier='smart' uses the 3b-cpu model
        response = self.neural.request_inference(prompt, tier="smart", format_json=True)
        try:
            return json.loads(response)
        except:
            return {"summary": response.strip()}
