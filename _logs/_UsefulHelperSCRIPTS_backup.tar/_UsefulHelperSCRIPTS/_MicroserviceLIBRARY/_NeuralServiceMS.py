import requests
import json
import concurrent.futures
import logging
from typing import Optional, Dict, Any, List
from microservice_std_lib import service_metadata, service_endpoint
OLLAMA_API_URL = 'http://localhost:11434/api'
logger = logging.getLogger('NeuralService')

@service_metadata(name='NeuralService', version='1.0.0', description='The Brain Interface: Orchestrates local AI operations via Ollama.', tags=['ai', 'neural', 'inference', 'ollama'], capabilities=['text-generation', 'embeddings', 'parallel-processing'], internal_dependencies=['microservice_std_lib'], external_dependencies=['requests'])
class NeuralServiceMS:
    """
    The Brain Interface: Orchestrates local AI operations via Ollama for inference and embeddings.
    """

    def __init__(self, config: Optional[Dict[str, Any]]=None):
        self.config = config or {}
        self.max_workers = self.config.get('max_workers', 4)
        self.models = {'fast': 'qwen2.5-coder:1.5b-cpu', 'smart': 'qwen2.5:3b-cpu', 'embed': 'mxbai-embed-large:latest-cpu'}
        if 'models' in self.config:
            self.models.update(self.config['models'])

    @service_endpoint(inputs={'fast_model': 'str', 'smart_model': 'str', 'embed_model': 'str'}, outputs={'status': 'str'}, description='Updates the active model configurations on the fly.', tags=['config', 'write'], side_effects=['config:update'])
    def update_models(self, fast_model: str, smart_model: str, embed_model: str) -> Dict[str, str]:
        """Called by the UI Settings Modal to change models on the fly."""
        self.models['fast'] = fast_model
        self.models['smart'] = smart_model
        self.models['embed'] = embed_model
        logger.info(f'Models Updated: Fast={fast_model}, Smart={smart_model}')
        return {'status': 'success', 'config': str(self.models)}

    @service_endpoint(inputs={}, outputs={'models': 'List[str]'}, description='Fetches a list of available models from the local Ollama instance.', tags=['ai', 'read'], side_effects=['network:read'])
    def get_available_models(self) -> List[str]:
        """Fetches list from Ollama for the UI dropdown."""
        try:
            res = requests.get(f'{OLLAMA_API_URL}/tags', timeout=2)
            if res.status_code == 200:
                return [m['name'] for m in res.json().get('models', [])]
        except Exception as e:
            logger.error(f'Failed to fetch models: {e}')
            return []
        return []

    @service_endpoint(inputs={}, outputs={'is_alive': 'bool'}, description='Pings Ollama to verify connectivity.', tags=['health', 'read'], side_effects=['network:read'])
    def check_connection(self) -> bool:
        """Pings Ollama to see if it's alive."""
        try:
            requests.get(f'{OLLAMA_API_URL}/tags', timeout=2)
            return True
        except requests.RequestException:
            logger.error("Ollama connection failed. Is 'ollama serve' running?")
            return False

    @service_endpoint(inputs={'text': 'str'}, outputs={'embedding': 'list'}, description='Generates a vector embedding for the provided text.', tags=['nlp', 'vector', 'ai'], side_effects=['network:read'])
    def get_embedding(self, text: str) -> Optional[List[float]]:
        """Generates a vector using the configured embedding model."""
        try:
            res = requests.post(f'{OLLAMA_API_URL}/embeddings', json={'model': self.models['embed'], 'prompt': text}, timeout=30)
            if res.status_code == 200:
                return res.json().get('embedding')
        except Exception as e:
            logger.error(f'Embedding failed: {e}')
        return None

    @service_endpoint(inputs={'prompt': 'str', 'tier': 'str', 'format_json': 'bool'}, outputs={'response': 'str'}, description='Requests synchronous text generation from a local LLM.', tags=['llm', 'inference'], side_effects=['network:read'])
    def request_inference(self, prompt: str, tier: str='fast', format_json: bool=False) -> str:
        """
        Synchronous inference request.
        tier: 'fast', 'smart', or other keys in self.models
        """
        model = self.models.get(tier, self.models['fast'])
        payload = {'model': model, 'prompt': prompt, 'stream': False}
        if format_json:
            payload['format'] = 'json'
        try:
            res = requests.post(f'{OLLAMA_API_URL}/generate', json=payload, timeout=60)
            if res.status_code == 200:
                return res.json().get('response', '').strip()
        except Exception as e:
            logger.error(f'Inference ({tier}) failed: {e}')
        return ''

    def process_parallel(self, items: List[Any], worker_func) -> List[Any]:
        """
        Helper to run a function across many items using a ThreadPool.
        Useful for batch ingestion.
        Note: Not exposed as an endpoint as it takes a function as an argument.
        """
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(worker_func, item): item for item in items}
            for future in concurrent.futures.as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as e:
                    logger.error(f'Worker task failed: {e}')
        return results
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    svc = NeuralServiceMS()
    print('Service ready:', svc)
    if svc.check_connection():
        print('Ollama Connection: OK')
        print(f'Models available: {svc.get_available_models()}')
        print('Testing Inference (Fast Tier)...')
        response = svc.request_inference('Why is the sky blue? Answer in 1 sentence.')
        print(f'Response: {response}')
    else:
        print('Ollama Connection: FAILED (Is Ollama running?)')
