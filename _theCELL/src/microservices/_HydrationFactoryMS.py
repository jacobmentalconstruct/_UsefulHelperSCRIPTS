"""
SERVICE_NAME: _HydrationFactoryMS
ENTRY_POINT: _HydrationFactoryMS.py
INTERNAL_DEPENDENCIES: base_service, microservice_std_lib, _CodeFormatterMS, _TreeMapperMS, _VectorFactoryMS
EXTERNAL_DEPENDENCIES: None
"""
import os
import json
import logging
from typing import Dict, Any, Optional, List, Union
from .microservice_std_lib import service_metadata, service_endpoint
from .base_service import BaseService

@service_metadata(
    name='HydrationFactory',
    version='1.0.0',
    description='The Fabricator: Converts raw Cell Artifacts into hydrated, usable products (Files, Maps, Memories).',
    tags=['utility', 'converter', 'factory', 'output'],
    capabilities=['filesystem:write', 'compute', 'db:vector'],
    side_effects=['filesystem:write', 'db:write'],
    internal_dependencies=['base_service', 'microservice_std_lib', '_CodeFormatterMS', '_TreeMapperMS', '_VectorFactoryMS']
)
class HydrationFactoryMS(BaseService):
    """
    The Fabricator.
    Takes a raw JSON Artifact from a Cell and "Hydrates" it into a final product
    based on the requested mode.
    
    Modes:
    1. SCAFFOLD (Code): Formats and writes source code to disk.
    2. BLUEPRINT (Doc): Generates a project tree map.
    3. MEMORY (Vector): Embeds the artifact into a Vector Store (Long-term memory).
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, services: Optional[Dict[str, Any]] = None):
        super().__init__('HydrationFactory')
        self.config = config or {}
        self.services = services or {}

        # Specialists are injected by the orchestration layer.
        # Expected keys: formatter, mapper, vector_factory, ingest_engine
        self.formatter = self.services.get('formatter')
        self.mapper = self.services.get('mapper')
        self.vector_factory = self.services.get('vector_factory')
        self.ingest_engine = self.services.get('ingest_engine')

    @service_endpoint(
        inputs={'artifact': 'Dict', 'mode': 'str', 'destination': 'str'},
        outputs={'status': 'str', 'details': 'Dict'},
        description='Main entry point to hydrate an artifact into a concrete product.',
        tags=['factory', 'execute']
    )
    # ROLE: Main entry point to hydrate an artifact into a concrete product.
    # INPUTS: {"artifact": "Dict", "destination": "str", "mode": "str"}
    # OUTPUTS: {"details": "Dict", "status": "str"}
    def hydrate_artifact(self, artifact: Dict[str, Any], mode: str, destination: str) -> Dict[str, Any]:
        """
        :param artifact: The standardized JSON output from a Cell.
        :param mode: 'scaffold', 'blueprint', or 'memory'.
        :param destination: File path (for scaffold/blueprint) or Collection name (for memory).
        """
        self.log_info(f"Hydrating artifact via mode: {mode.upper()} -> {destination}")
        
        try:
            if mode.lower() == 'scaffold':
                return self._hydrate_scaffold(artifact, destination)
            elif mode.lower() == 'blueprint':
                return self._hydrate_blueprint(destination)
            elif mode.lower() == 'memory':
                return self._hydrate_memory(artifact, destination)
            else:
                raise ValueError(f"Unknown hydration mode: {mode}")
        except Exception as e:
            self.log_error(f"Hydration failed: {e}")
            return {"status": "error", "message": str(e)}

    def _hydrate_scaffold(self, artifact: Dict[str, Any], file_path: str) -> Dict[str, Any]:
        """Writes the payload to a file after passing it through the CodeFormatter."""
        content = artifact.get('payload', '')
        if not content:
            return {"status": "skipped", "reason": "Empty payload"}

        # 1. Format the code (The Architect)
        # We assume Python for now, but this could be dynamic based on extension
        formatted_result = self.formatter.normalize_code(content, spaces=4)
        final_code = formatted_result.get('normalized', content)
        hunks_applied = len(formatted_result.get('patch', {}).get('hunks', []))

        # 2. Write to disk
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(final_code)

        return {
            "status": "success",
            "type": "file_write",
            "path": file_path,
            "formatting_hunks_applied": hunks_applied
        }

    def _hydrate_blueprint(self, root_path: str) -> Dict[str, Any]:
        """Generates a project tree map and saves it to a file."""
        # 1. Generate Map (The Cartographer)
        tree_map = self.mapper.generate_tree(root_path)
        
        # 2. Save to _project_map.txt in the root
        output_path = os.path.join(root_path, '_project_map.txt')
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(tree_map)

        return {
            "status": "success",
            "type": "map_generation",
            "path": output_path,
            "size": len(tree_map)
        }

    def _hydrate_memory(self, artifact: Dict[str, Any], collection_name: str) -> Dict[str, Any]:
        """Embeds the artifact payload into the Vector Store."""
        # 1. Create Vector Store Connection (The Switchboard)
        # Defaulting to Chroma for persistence, could be config-driven
        store = self.vector_factory.create('chroma', {'path': './knowledge_base', 'collection': collection_name})
        
        # 2. Prepare Data
        # We embed the payload (content) and attach the metadata
        payload = artifact.get('payload', '')
        if not payload:
             return {"status": "skipped", "reason": "Empty payload"}
             
        # Generate a simple embedding (Mocked here, normally uses IngestEngine or internal embedder)
        # In a real flow, we'd call an embedding service. 
        # For the factory, we assume the artifact might already have a vector, 
        # or we generate a placeholder/call a service if we want to be fully self-contained.
        # SIMPLIFICATION: We will require the embedding to be passed or we skip it for this stub.
        # Ideally, we call self.ingest_engine.get_embedding(payload)
        
        # For now, we just store the text without vector search if no embedding provided (Chroma handles raw text too usually)
        # But our VectorStore protocol expects embeddings.
        # ENGINE: injected by orchestration layer
        if not getattr(self, 'ingest_engine', None):
            return {"status": "error", "message": "IngestEngine not injected"}

        engine = self.ingest_engine
        # We use a standard small model for embeddings (e.g., all-minilm)
        vector = engine._get_embedding(model="nomic-embed-text", text=payload)
        
        if not vector:
            self.log_warning("Could not generate embedding, falling back to mock.")
            vector = [0.0] * 384

        store.add(
            embeddings=[vector],
            metadatas=[artifact.get('metadata', {})]
        )

        return {
            "status": "success",
            "type": "memory_storage",
            "collection": collection_name,
            "item_count": store.count()
        }

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    
    # Test Harness
    factory = HydrationFactoryMS()
    print(f"Service Ready: {factory}")
    
    # Mock Artifact
    test_artifact = {
        "metadata": {"author": "TheCell", "version": "1.0"},
        "payload": "def hello_world():\n  print('Hello from the Factory!')",
        "instructions": {"system_prompt": "Write python code"}
    }
    
    print("\n--- Testing Code Hydration ---")
    res = factory.hydrate_artifact(test_artifact, mode='scaffold', destination='./_test_output.py')
    print(json.dumps(res, indent=2))
    
    print("\n--- Testing Clean Up ---")
    if os.path.exists('./_test_output.py'):
        os.remove('./_test_output.py')
        print("Cleaned up test file.")


