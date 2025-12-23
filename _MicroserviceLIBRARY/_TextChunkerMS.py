import logging
from typing import Any, Dict, List, Optional, Tuple

from microservice_std_lib import service_metadata, service_endpoint

# ==============================================================================
# CONFIGURATION
# ==============================================================================
logger = logging.getLogger("TextChunker")

# ==============================================================================
# MICROSERVICE CLASS
# ==============================================================================

@service_metadata(
    name="TextChunker",
    version="1.0.0",
    description="Splits text into chunks using various strategies (chars, lines).",
    tags=["chunking", "nlp", "rag"],
    capabilities=["compute"]
)
class TextChunkerMS:
    """
    The Butcher: A unified service for splitting text into digestible chunks
    for RAG (Retrieval Augmented Generation).
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

    @service_endpoint(
        inputs={"text": "str", "chunk_size": "int", "chunk_overlap": "int"},
        outputs={"chunks": "List[str]"},
        description="Standard sliding window split by character count.",
        tags=["chunking", "chars"],
        side_effects=[]
    )
    def chunk_by_chars(self, text: str, chunk_size: int = 500, chunk_overlap: int = 50) -> List[str]:
        """
        Standard Sliding Window. Best for prose/documentation.
        Splits purely by character count.
        """
        if chunk_size <= 0: 
            raise ValueError("chunk_size must be positive")
        
        chunks = []
        start = 0
        text_length = len(text)

        while start < text_length:
            end = start + chunk_size
            chunk = text[start:end]
            chunks.append(chunk)
            
            # Stop if we've reached the end
            if end >= text_length:
                break
                
            # Advance start, backing up by overlap
            start += chunk_size - chunk_overlap
            
        return chunks

    @service_endpoint(
        inputs={"text": "str", "max_lines": "int", "max_chars": "int"},
        outputs={"chunks": "List[Dict]"},
        description="Line-preserving chunker, best for code.",
        tags=["chunking", "lines", "code"],
        side_effects=[]
    )
    def chunk_by_lines(self, text: str, max_lines: int = 200, max_chars: int = 4000) -> List[Dict[str, Any]]:
        """
        Line-Preserving Chunker. Best for Code.
        Respects line boundaries and returns metadata about line numbers.
        """
        lines = text.splitlines()
        chunks = []
        start = 0
        
        while start < len(lines):
            end = min(start + max_lines, len(lines))
            chunk_str = "\n".join(lines[start:end])
            
            # If too big, shrink window (back off)
            while len(chunk_str) > max_chars and end > start + 1:
                end -= 1
                chunk_str = "\n".join(lines[start:end])
            
            chunks.append({
                "text": chunk_str,
                "start_line": start + 1,
                "end_line": end
            })
            start = end
            
        return chunks


# --- Independent Test Block ---
if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    
    chunker = TextChunkerMS()
    print("Service ready:", chunker)
    
    # 1. Prose Test
    print("--- Prose Chunking ---")
    lorem = "A" * 100 # 100 chars
    result = chunker.chunk_by_chars(lorem, chunk_size=40, chunk_overlap=10)
    for i, c in enumerate(result):
        print(f"Chunk {i}: len={len(c)}")

    # 2. Code Test
    print("\n--- Code Chunking ---")
    code = "\n".join([f"print('Line {i}')" for i in range(1, 10)])
    # Force splits small for testing
    result_code = chunker.chunk_by_lines(code, max_lines=3, max_chars=100)
    for i, c in enumerate(result_code):
        print(f"Chunk {i}: Lines {c['start_line']}-{c['end_line']}")