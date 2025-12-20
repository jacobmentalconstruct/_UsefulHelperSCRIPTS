"""
SERVICE_NAME: _NeuralServiceMS
ENTRY_POINT: __NeuralServiceMS.py
DEPENDENCIES: None
"""

import requests
import json
import concurrent.futures
from typing import Optional, Dict, Any, List
from base_service import BaseService
from microservice_std_lib import service_metadata, service_endpoint

# Configuration constants
OLLAMA_API_URL = "http://localhost:11434/api"

@service_metadata(
    name="NeuralServiceMS",
    version="1.0.0",
    description="The Brain Interface: Orchestrates local AI operations via Ollama for inference and embeddings.",
    tags=["ai", "neural", "inference", "ollama"],
    capabilities=["text-generation", "embeddings", "parallel-processing"]
)
class NeuralServiceMS(BaseService):
    def __init__(self, max_workers: int = 4):
        super().__init__("NeuralServiceMS")
        self.max_workers = max_workers
        # Default configs
        self.config = {
            "fast": "qwen2.5-coder:1.5b-cpu",
            "smart": "qwen2.5:3b-cpu",
            "embed": "mxbai-embed-large:latest-cpu"
        }

    def update_models(self, fast_model: str, smart_model: str, embed_model: str):
        """Called by the UI Settings Modal to change models on the fly."""
        self.config["fast"] = fast_model
        self.config["smart"] = smart_model
        self.config["embed"] = embed_model
        self.log_info(f"Models Updated: Fast={fast_model}, Smart={smart_model}")

    def get_available_models(self) -> List[str]:
        """Fetches list from Ollama for the UI dropdown."""
        try:
            res = requests.get(f"{OLLAMA_API_URL}/tags", timeout=2)
            if res.status_code == 200:
                return [m['name'] for m in res.json().get('models', [])]
        except:
            return []
        return []

    def check_connection(self) -> bool:
        """Pings Ollama to see if it's alive."""
        try:
            requests.get(f"{OLLAMA_API_URL}/tags", timeout=2)
            return True
        except requests.RequestException:
            self.log_error("Ollama connection failed. Is 'ollama serve' running?")
            return False

    @service_endpoint(
        inputs={"text": "str"},
        outputs={"embedding": "list"},
        description="Generates a high-dimensional vector embedding for the provided text using the configured model.",
        tags=["nlp", "vector"]
    )
    def get_embedding(self, text: str) -> Optional[List[float]]:
        """Generates a vector using the CPU embedder."""
        try:
            res = requests.post(
                f"{OLLAMA_API_URL}/embeddings",
                json={"model": self.config["embed"], "prompt": text},
                timeout=30
            )
            if res.status_code == 200:
                return res.json().get("embedding")
        except Exception as e:
            self.log_error(f"Embedding failed: {e}")
        return None

    @service_endpoint(
        inputs={"prompt": "str", "tier": "str", "format_json": "bool"},
        outputs={"response": "str"},
        description="Requests a synchronous text generation/inference from a local LLM tier.",
        tags=["llm", "inference"]
    )
    def request_inference(self, prompt: str, tier: str = "fast", format_json: bool = False) -> str:
        """
        Synchronous inference request.
        tier: 'fast' (1.5b-cpu), 'smart' (3b-cpu), or 'architect' (7b-gpu)
        """
        model = self.config.get(tier, self.config["fast"])
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

                    if __name__ == "__main__":
                        svc = NeuralServiceMS()
                        print("Service ready:", svc._service_info["name"])
                        if svc.check_connection():
                            print("Ollama Connection: OK")
                        else:
                            print("Ollama Connection: FAILED")


