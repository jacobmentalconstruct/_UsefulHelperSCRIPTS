import requests
import json
import concurrent.futures
from typing import Optional, Dict, Any, List
from .base_service import BaseService

# Configuration constants
OLLAMA_API_URL = "http://localhost:11434/api"

class NeuralService(BaseService):
    """
    Manages connections to the Neural Backend (Ollama).
    Handles Tiering (CPU vs GPU) and Parallelism.
    """
    
    # Define our tiers based on the 'Bake' script we ran earlier
    MODELS = {
        "fast": "qwen2.5-coder:1.5b-cpu",     # The Roughneck (CPU)
        "smart": "qwen2.5:3b-cpu",            # The Supervisor (CPU)
        "architect": "qwen2.5:7b",            # The Big Brain (GPU)
        "embed": "mxbai-embed-large:latest-cpu" # The Embedder (CPU)
    }

    def __init__(self, max_workers: int = 4):
        super().__init__("NeuralService")
        self.max_workers = max_workers
        self.log_info(f"Neural Link Active. CPU Workers: {max_workers}")

    def check_connection(self) -> bool:
        """Pings Ollama to see if it's alive."""
        try:
            requests.get(f"{OLLAMA_API_URL}/tags", timeout=2)
            return True
        except requests.RequestException:
            self.log_error("Ollama connection failed. Is 'ollama serve' running?")
            return False

    def get_embedding(self, text: str) -> Optional[List[float]]:
        """Generates a vector using the CPU embedder."""
        try:
            res = requests.post(
                f"{OLLAMA_API_URL}/embeddings",
                json={"model": self.MODELS["embed"], "prompt": text},
                timeout=30
            )
            if res.status_code == 200:
                return res.json().get("embedding")
        except Exception as e:
            self.log_error(f"Embedding failed: {e}")
        return None

    def request_inference(self, prompt: str, tier: str = "fast", format_json: bool = False) -> str:
        """
        Synchronous inference request.
        tier: 'fast' (1.5b-cpu), 'smart' (3b-cpu), or 'architect' (7b-gpu)
        """
        model = self.MODELS.get(tier, self.MODELS["fast"])
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False
        }
        if format_json:
            payload["format"] = "json"

        try:
            res = requests.post(f"{OLLAMA_API_URL}/generate", json=payload, timeout=60)
            if res.status_code == 200:
                return res.json().get("response", "").strip()
        except Exception as e:
            self.log_error(f"Inference ({tier}) failed: {e}")
        return ""

    def process_parallel(self, items: List[Any], worker_func) -> List[Any]:
        """
        Helper to run a function across many items using the ThreadPool.
        Useful for batch ingestion.
        """
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # worker_func should take a single item and return a result
            futures = {executor.submit(worker_func, item): item for item in items}
            for future in concurrent.futures.as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as e:
                    self.log_error(f"Worker task failed: {e}")
        return results
