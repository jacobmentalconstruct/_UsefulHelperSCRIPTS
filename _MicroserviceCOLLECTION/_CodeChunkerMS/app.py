import re
from typing import List, Dict, Any, Optional
from pathlib import Path
from microservice_std_lib import service_metadata, service_endpoint

@service_metadata(
name="CodeChunker",
version="1.0.0",
description="Splits code into semantic blocks (Classes, Functions) using indentation and regex heuristics.",
tags=["parsing", "chunking", "code"],
capabilities=["filesystem:read"]
)
class CodeChunkerMS:
    """
The Surgeon (Pure Python Edition): Splits code into semantic blocks
    (Classes, Functions) using indentation and regex heuristics.
    
    Advantages: Zero dependencies. Works on any machine.
    Disadvantages: Slightly less precise than Tree-Sitter for messy code.
    """
    def __init__(self, config: Optional[Dict[str, Any]] = None):
    self.config = config or {}
    # Regex to find definitions. Capture group 1 is the indentation.
    # Supports Python, JS, TS, Go signatures loosely.
        self.def_pattern = re.compile(
            r'^(\s*)(?:async\s+)?(?:class|def|function|func|var|const)\s+([a-zA-Z0-9_]+)', 
            re.MULTILINE
        )

    @service_endpoint(
    inputs={"file_path": "str", "max_chars": "int"},
    outputs={"chunks": "List[Dict]"},
    description="Reads a file and breaks it into logical blocks based on indentation.",
    tags=["parsing", "chunking"],
    side_effects=["filesystem:read"]
    )
    def chunk_file(self, file_path: str, max_chars: int = 1500) -> List[Dict[str, Any]]:
    """
    Reads a file and breaks it into logical blocks based on indentation.
    """
        path = Path(file_path)
        try:
            code = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            return []

        return self._chunk_by_indentation(code, max_chars)

    def _chunk_by_indentation(self, code: str, max_chars: int) -> List[Dict]:
lines = code.splitlines()
        chunks = []
        
        current_chunk_lines = []
        current_start_line = 0
        current_indent = 0
        in_block = False
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # 1. Skip empty lines if we aren't in a block
            if not stripped and not in_block:
                continue

            # 2. Calculate Indentation
            indent_match = re.match(r'^(\s*)', line)
            indent_level = len(indent_match.group(1)) if indent_match else 0

            # 3. Check for Block Start (def/class at root level or low indent)
            # We allow indent < 4 spaces to catch top-level stuff or slight nesting
            match = self.def_pattern.match(line)
            is_def = match is not None and indent_level <= 4
            
            # IF we hit a new definition AND we have a chunk pending:
            if is_def and current_chunk_lines:
                # Save previous chunk
                self._finalize_chunk(chunks, current_chunk_lines, current_start_line, max_chars)
                # Reset
                current_chunk_lines = []
                current_start_line = i + 1
                in_block = True
                current_indent = indent_level

            # IF we hit a line with LESS indentation than the current block start,
            # the block has ended. (Python/Yaml logic, mostly holds for C-style too if formatted)
            if in_block and stripped and indent_level <= current_indent and not is_def:
                # Special case: Closing braces '}' often have same indent as start
                if not stripped.startswith('}'):
                    self._finalize_chunk(chunks, current_chunk_lines, current_start_line, max_chars)
                    current_chunk_lines = []
                    current_start_line = i + 1
                    in_block = False

            current_chunk_lines.append(line)

        # Flush remaining
        if current_chunk_lines:
            self._finalize_chunk(chunks, current_chunk_lines, current_start_line, max_chars)

        return chunks

    def _finalize_chunk(self, chunks, lines, start_line, max_chars):
        """Recursively splits huge chunks if they exceed max_chars."""
        full_text = "\n".join(lines)
        if not full_text.strip(): return

        # If chunk is too big, split it by lines (naive fallback for massive functions)
        if len(full_text) > max_chars:
            self._split_large_block(chunks, lines, start_line, max_chars)
        else:
            chunks.append({
                "type": "block", # Generic type since we aren't parsing AST
                "text": full_text,
                "start_line": start_line,
                "end_line": start_line + len(lines)
            })

    def _split_large_block(self, chunks, lines, start_line, max_chars):
        """Force split a large block while keeping line boundaries."""
        current_sub = []
        current_len = 0
        sub_start = start_line
        
        for i, line in enumerate(lines):
            if current_len + len(line) > max_chars:
                if current_sub:
                    chunks.append({
                        "type": "fragment",
                        "text": "\n".join(current_sub),
                        "start_line": sub_start,
                        "end_line": sub_start + len(current_sub)
                    })
                current_sub = []
                current_len = 0
                sub_start = start_line + i
            
            current_sub.append(line)
            current_len += len(line)
            
        if current_sub:
            chunks.append({
                "type": "fragment",
                "text": "\n".join(current_sub),
                "start_line": sub_start,
                "end_line": sub_start + len(current_sub)
            })

# --- Independent Test Block ---
if __name__ == "__main__":
chunker = CodeChunkerMS()
print("Service ready:", chunker)
    
# Test Python Code
    py_code = """
import os

def small_helper():
    return True

class DataProcessor:
    def __init__(self):
        self.data = []

    def process(self, raw_input):
        # This is a comment inside the function
        if raw_input:
            self.data.append(raw_input)
        return True
    """
    
    # Write temp file
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w+", delete=False) as tmp:
        tmp.write(py_code)
        tmp_path = tmp.name
        
    print(f"--- Chunking {tmp_path} (Pure Python) ---")
    chunks = chunker.chunk_file(tmp_path)
    
    for i, c in enumerate(chunks):
        print(f"\n[Chunk {i}] Lines {c['start_line']}-{c['end_line']}")
        print(f"{'-'*20}\n{c['text'].strip()}\n{'-'*20}")
        
    os.remove(tmp_path)
