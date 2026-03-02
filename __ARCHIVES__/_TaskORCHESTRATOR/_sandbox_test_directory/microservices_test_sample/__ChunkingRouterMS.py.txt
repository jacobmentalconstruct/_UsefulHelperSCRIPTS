"""
SERVICE_NAME: _ChunkingRouterMS
ENTRY_POINT: __ChunkingRouterMS.py
DEPENDENCIES: None
"""

import re
from typing import Any, Dict, List, Optional
from microservice_std_lib import service_metadata, service_endpoint
from __PythonChunkerMS import PythonChunkerMS, CodeChunk

@service_metadata(
    name="ChunkingRouterMS",
    version="1.1.0",
    description="The Dispatcher: Routes files to specialized chunkers based on extension (AST for Python, Recursive for Prose).",
    tags=["orchestration", "chunking", "nlp"],
    capabilities=["routing", "text-processing"]
)
class ChunkingRouterMS:
    """
The Editor: A 'Recursive' text splitter.
It respects the natural structure of text (Paragraphs -> Sentences -> Words)
rather than just hacking it apart by character count.
"""
    
def __init__(self, config: Optional[Dict[str, Any]] = None):
    self.config = config or {}
    self.python_specialist = PythonChunkerMS()
    # Separators for the Prose Specialist logic
    self.separators = ["\n\n", "\n", "(?<=[.?!])\s+", " ", ""]

    @service_endpoint(
        inputs={"text": "str", "filename": "str", "max_size": "int", "overlap": "int"},
        outputs={"chunks": "list"},
        description="Routes text to the appropriate specialist. Returns a list of CodeChunk objects or raw strings.",
        tags=["routing", "chunking"]
    )
    def chunk_file(self, text: str, filename: str, max_size: int = 1000, overlap: int = 100) -> List[Any]:
        """
        Extension-aware router.
        """
        if filename.endswith(".py"):
            return self.python_specialist.chunk(text)
        
        # Fallback to the internal Prose Specialist (Recursive Splitter)
        raw_chunks = self._recursive_split(text, self.separators, max_size, overlap)
        
        # Standardize output for the Refinery: Wrap prose in CodeChunk objects
        return [
            CodeChunk(
                name=f"prose_chunk_{i}", 
                type="text", 
                content=c, 
                start_line=0, 
                end_line=0
            ) for i, c in enumerate(raw_chunks)
        ]

    def _recursive_split(self, text: str, separators: List[str], max_size: int, overlap: int) -> List[str]:
        final_chunks = []
        
        # 1. Base Case: If the text fits, return it
        if len(text) <= max_size:
            return [text]
        
        # 2. Edge Case: No more separators, forced hard split
        if not separators:
            return self._hard_split(text, max_size, overlap)

        # 3. Recursive Step: Try to split by the current separator
        current_sep = separators[0]
        next_separators = separators[1:]
        
        # Regex split to keep delimiters if possible (logic varies by regex complexity)
        # For simple string splits like \n\n, we just split.
        if len(current_sep) > 1 and "(" in current_sep: 
            # It's a regex lookbehind (sentence splitter), use re.split
            splits = re.split(current_sep, text)
        else:
            splits = text.split(current_sep)

        # Now we have a list of smaller pieces. We need to merge them back together
        # until they fill the 'max_size' bucket, then start a new bucket.
        current_doc = []
        current_length = 0
        
        for split in splits:
            if not split: continue
            
            # If a single split is STILL too big, recurse deeper on it
            if len(split) > max_size:
                # If we have stuff in the buffer, flush it first
                if current_doc:
                    final_chunks.append(current_sep.join(current_doc))
                    current_doc = []
                    current_length = 0
                
                # Recurse on the big chunk using the NEXT separator
                sub_chunks = self._recursive_split(split, next_separators, max_size, overlap)
                final_chunks.extend(sub_chunks)
                continue

            # Check if adding this split would overflow
            if current_length + len(split) + len(current_sep) > max_size:
                # Flush the current buffer
                doc_text = current_sep.join(current_doc)
                final_chunks.append(doc_text)
# Start new buffer with overlap logic?
                # For simplicity in recursion, we often just start fresh or carry over 
                # a small tail if we implemented a rolling window here.
                # To keep this "Pure logic" simple, we start fresh with the current split.
                current_doc = [split]
                current_length = len(split)
            else:
                # Add to buffer
                current_doc.append(split)
                current_length += len(split) + len(current_sep)

        # Flush remaining
        if current_doc:
            final_chunks.append(current_sep.join(current_doc))

        return final_chunks

    def _hard_split(self, text: str, chunk_size: int, overlap: int) -> List[str]:
        """Last resort: naive character sliding window."""
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunks.append(text[start:end])
            start += chunk_size - overlap
        return chunks

# --- Independent Test Block ---
if __name__ == "__main__":
    chunker = SmartChunkerMS()
    print("Service ready:", chunker)
    
    # Example: A technical document with structure
    doc = """
    # Intro to AI
    Artificial Intelligence is great. It helps us code.
    
    ## How it works
    1. Ingestion: Reading data.
    2. Processing: Thinking about data.
    
    This is a very long paragraph that effectively serves as a stress test for the sentence splitter. It should hopefully not break in the middle of a thought! We want to keep sentences whole.
    """
    
    print("--- Testing Smart Chunking (Max 60 chars) ---")
    # We set max_size very small to force it to use the sentence/word splitters
    chunks = chunker.chunk(doc, max_size=60, overlap=0)
    
    for i, c in enumerate(chunks):
        print(f"[{i}] {repr(c)}")

