"""
Tree-sitter based code chunker for multi-language support.

Provides AST-based chunking for 20+ programming languages using tree-sitter.
Falls back to prose chunker if parsing fails or language is unsupported.

Four-tier language classification:
  deep_semantic   — Python, JS, TS, Java, Go, Rust, C++, C#, etc.
                    Full class → method → nested function hierarchy.
  shallow_semantic — Bash, R, Ruby, PHP, C.
                    Functions only, max semantic depth = 1.
  structural      — JSON, YAML, TOML.
                    Key-value nesting with no code semantics.
  hybrid          — HTML, CSS, XML.
                    Structural markup, not executable code hierarchy.

Extracted from: TripartiteDataSTORE/src/chunkers/treesitter.py
Rewritten for Graph Manifold ingestion pipeline.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .chunking import RawChunk
from .config import (
    DEFAULT_MAX_CHUNK_TOKENS,
    DEFAULT_OVERLAP_LINES,
    EXT_TO_LANGUAGE,
    IngestionConfig,
    get_language_tier,
)
from .detection import SourceFile, estimate_tokens

logger = logging.getLogger(__name__)


# ── Tree-sitter availability (lazy import) ────────────────────────────────────

def _tree_sitter_available() -> bool:
    """Check if tree-sitter and language pack are importable."""
    try:
        import tree_sitter_language_pack  # noqa: F401
        return True
    except ImportError:
        return False


def _get_parser(language: str) -> Optional[Any]:
    """
    Create a tree-sitter parser for the given language.
    Returns None if tree-sitter is unavailable or language unsupported.
    """
    try:
        from tree_sitter import Parser
        from tree_sitter_language_pack import get_language

        parser = Parser()
        parser.language = get_language(language)
        return parser
    except Exception:
        return None


def _run_query(language: str, query_str: str, node: Any) -> List[tuple]:
    """Run a tree-sitter query and return captures."""
    try:
        from tree_sitter_language_pack import get_language

        lang = get_language(language)
        query = lang.query(query_str)
        return query.captures(node)
    except Exception:
        return []


# ── Tree-sitter query patterns ────────────────────────────────────────────────
# Extracted from: TripartiteDataSTORE/src/chunkers/treesitter.py :: FUNCTION_QUERIES, CLASS_QUERIES, IMPORT_QUERIES

FUNCTION_QUERIES: Dict[str, str] = {
    "python": """
        (function_definition
            name: (identifier) @name) @function
        (decorated_definition
            definition: (function_definition
                name: (identifier) @name)) @function
    """,
    "javascript": """
        (function_declaration
            name: (identifier) @name) @function
        (function
            name: (identifier) @name) @function
        (method_definition
            name: (property_identifier) @name) @method
        (arrow_function) @function
    """,
    "typescript": """
        (function_declaration
            name: (identifier) @name) @function
        (function_signature
            name: (identifier) @name) @function
        (method_definition
            name: (property_identifier) @name) @method
        (method_signature
            name: (property_identifier) @name) @method
        (arrow_function) @function
    """,
    "java": """
        (method_declaration
            name: (identifier) @name) @method
        (constructor_declaration
            name: (identifier) @name) @constructor
    """,
    "go": """
        (function_declaration
            name: (identifier) @name) @function
        (method_declaration
            name: (field_identifier) @name) @method
    """,
    "rust": """
        (function_item
            name: (identifier) @name) @function
        (function_signature_item
            name: (identifier) @name) @function
    """,
    "c": """
        (function_definition
            declarator: (function_declarator
                declarator: (identifier) @name)) @function
    """,
    "cpp": """
        (function_definition
            declarator: (function_declarator
                declarator: (identifier) @name)) @function
        (function_definition
            declarator: (function_declarator
                declarator: (qualified_identifier
                    name: (identifier) @name))) @function
    """,
    "c_sharp": """
        (method_declaration
            name: (identifier) @name) @method
        (constructor_declaration
            name: (identifier) @name) @constructor
    """,
    "ruby": """
        (method
            name: (identifier) @name) @method
        (singleton_method
            name: (identifier) @name) @method
    """,
    "php": """
        (function_definition
            name: (name) @name) @function
        (method_declaration
            name: (name) @name) @method
    """,
    "swift": """
        (function_declaration
            name: (simple_identifier) @name) @function
    """,
    "kotlin": """
        (function_declaration
            (simple_identifier) @name) @function
    """,
    "scala": """
        (function_definition
            name: (identifier) @name) @function
    """,
    "bash": """
        (function_definition
            name: (word) @name) @function
    """,
}


CLASS_QUERIES: Dict[str, str] = {
    "python": """
        (class_definition
            name: (identifier) @name) @class
    """,
    "javascript": """
        (class_declaration
            name: (identifier) @name) @class
    """,
    "typescript": """
        (class_declaration
            name: (type_identifier) @name) @class
    """,
    "java": """
        (class_declaration
            name: (identifier) @name) @class
        (interface_declaration
            name: (identifier) @name) @interface
        (enum_declaration
            name: (identifier) @name) @enum
    """,
    "go": """
        (type_declaration
            (type_spec
                name: (type_identifier) @name)) @type
    """,
    "rust": """
        (struct_item
            name: (type_identifier) @name) @struct
        (enum_item
            name: (type_identifier) @name) @enum
        (trait_item
            name: (type_identifier) @name) @trait
        (impl_item) @impl
    """,
    "c": """
        (struct_specifier
            name: (type_identifier) @name) @struct
        (enum_specifier
            name: (type_identifier) @name) @enum
    """,
    "cpp": """
        (class_specifier
            name: (type_identifier) @name) @class
        (struct_specifier
            name: (type_identifier) @name) @struct
    """,
    "c_sharp": """
        (class_declaration
            name: (identifier) @name) @class
        (interface_declaration
            name: (identifier) @name) @interface
        (struct_declaration
            name: (identifier) @name) @struct
    """,
    "ruby": """
        (class
            name: (constant) @name) @class
        (module
            name: (constant) @name) @module
    """,
    "php": """
        (class_declaration
            name: (name) @name) @class
        (interface_declaration
            name: (name) @name) @interface
        (trait_declaration
            name: (name) @name) @trait
    """,
    "swift": """
        (class_declaration
            name: (type_identifier) @name) @class
        (struct_declaration
            name: (type_identifier) @name) @struct
        (enum_declaration
            name: (type_identifier) @name) @enum
        (protocol_declaration
            name: (type_identifier) @name) @protocol
    """,
    "kotlin": """
        (class_declaration
            (type_identifier) @name) @class
        (object_declaration
            (type_identifier) @name) @object
    """,
    "scala": """
        (class_definition
            name: (identifier) @name) @class
        (object_definition
            name: (identifier) @name) @object
        (trait_definition
            name: (identifier) @name) @trait
    """,
}


IMPORT_QUERIES: Dict[str, str] = {
    "python": """
        (import_statement) @import
        (import_from_statement) @import
    """,
    "javascript": "(import_statement) @import",
    "typescript": "(import_statement) @import",
    "java": "(import_declaration) @import",
    "go": "(import_declaration) @import",
    "rust": "(use_declaration) @import",
    "c": "(preproc_include) @import",
    "cpp": "(preproc_include) @import",
    "c_sharp": "(using_directive) @import",
    "ruby": """
        (call
            method: (identifier) @method
            (#match? @method "^(require|require_relative|load|import)$")) @import
    """,
    "php": "(namespace_use_declaration) @import",
    "swift": "(import_declaration) @import",
    "kotlin": "(import_header) @import",
    "scala": "(import_declaration) @import",
}


# ── Node name extraction ─────────────────────────────────────────────────────

_NAME_NODE_TYPES = frozenset({
    "identifier", "property_identifier", "field_identifier",
    "type_identifier", "simple_identifier", "name", "word", "constant",
})


def _get_node_name(node: Any) -> Optional[str]:
    """Extract the name identifier from a tree-sitter node."""
    for child in node.children:
        if child.type in _NAME_NODE_TYPES:
            return child.text.decode("utf-8")
    name_child = node.child_by_field_name("name")
    if name_child:
        return name_child.text.decode("utf-8")
    return None


# ── Extraction helpers ────────────────────────────────────────────────────────

def _extract_imports(
    language: str, tree: Any, source: SourceFile, base_path: List[str],
) -> List[RawChunk]:
    """Extract import/include statements and consolidate into one chunk."""
    query_str = IMPORT_QUERIES.get(language)
    if not query_str or tree is None:
        return []

    captures = _run_query(language, query_str, tree.root_node)
    if not captures:
        return []

    import_lines: set = set()
    for node, _ in captures:
        import_lines.update(range(node.start_point[0], node.end_point[0] + 1))

    if not import_lines:
        return []

    sorted_lines = sorted(import_lines)
    lo, hi = sorted_lines[0], sorted_lines[-1]
    chunk_text = "\n".join(source.lines[lo : hi + 1])

    return [RawChunk(
        text=chunk_text,
        chunk_type="import_block",
        name="imports",
        heading_path=base_path + ["imports"],
        line_start=lo,
        line_end=hi,
        semantic_depth=1,
        structural_depth=1,
    )]


def _extract_functions(
    language: str, tree: Any, source: SourceFile,
    base_path: List[str], depth: int = 1,
) -> List[RawChunk]:
    """Extract top-level function definitions (not inside classes)."""
    query_str = FUNCTION_QUERIES.get(language)
    if not query_str or tree is None:
        return []

    captures = _run_query(language, query_str, tree.root_node)
    chunks: List[RawChunk] = []
    seen_ids: set = set()

    _CLASS_PARENT_TYPES = frozenset({
        "class_definition", "class_declaration", "class_specifier",
        "struct_specifier", "impl_item",
    })

    for node, capture_name in captures:
        if capture_name == "name":
            continue
        if id(node) in seen_ids:
            continue

        # Check if this is a top-level function (not inside a class)
        parent = node.parent
        in_class = False
        while parent:
            if parent.type in _CLASS_PARENT_TYPES:
                in_class = True
                break
            parent = parent.parent

        if in_class:
            continue

        seen_ids.add(id(node))
        name = _get_node_name(node)
        if not name:
            continue

        lo = node.start_point[0]
        hi = node.end_point[0]
        chunk_text = "\n".join(source.lines[lo : hi + 1])

        chunks.append(RawChunk(
            text=chunk_text,
            chunk_type="function_def",
            name=name,
            heading_path=base_path + [f"{name}()"],
            line_start=lo,
            line_end=hi,
            semantic_depth=depth,
            structural_depth=depth,
        ))

    return chunks


def _extract_classes(
    language: str, tree: Any, source: SourceFile, base_path: List[str],
) -> List[RawChunk]:
    """Extract class definitions and their methods."""
    query_str = CLASS_QUERIES.get(language)
    if not query_str or tree is None:
        return []

    captures = _run_query(language, query_str, tree.root_node)
    chunks: List[RawChunk] = []
    seen_ids: set = set()

    for node, capture_name in captures:
        if capture_name == "name":
            continue
        if id(node) in seen_ids:
            continue
        seen_ids.add(id(node))

        name = _get_node_name(node)
        if not name:
            continue

        lo = node.start_point[0]
        hi = node.end_point[0]

        # Class header chunk (signature + docstring, capped at 10 lines)
        header_end = min(lo + 10, hi)
        header_text = "\n".join(source.lines[lo : header_end + 1])
        class_path = base_path + [f"class {name}"]

        chunks.append(RawChunk(
            text=header_text,
            chunk_type=capture_name,
            name=name,
            heading_path=class_path,
            line_start=lo,
            line_end=header_end,
            semantic_depth=1,
            structural_depth=1,
        ))

        # Extract methods within this class
        method_chunks = _extract_methods(
            language, node, source, class_path, depth=2,
        )
        chunks.extend(method_chunks)

    return chunks


def _extract_methods(
    language: str, class_node: Any, source: SourceFile,
    parent_path: List[str], depth: int,
) -> List[RawChunk]:
    """Extract method definitions from within a class node."""
    query_str = FUNCTION_QUERIES.get(language)
    if not query_str:
        return []

    captures = _run_query(language, query_str, class_node)
    chunks: List[RawChunk] = []
    seen_ids: set = set()

    for node, capture_name in captures:
        if capture_name == "name":
            continue
        if id(node) in seen_ids:
            continue
        seen_ids.add(id(node))

        name = _get_node_name(node)
        if not name:
            continue

        lo = node.start_point[0]
        hi = node.end_point[0]
        chunk_text = "\n".join(source.lines[lo : hi + 1])

        chunks.append(RawChunk(
            text=chunk_text,
            chunk_type="method_def",
            name=name,
            heading_path=parent_path + [f"{name}()"],
            line_start=lo,
            line_end=hi,
            semantic_depth=depth,
            structural_depth=depth,
        ))

    return chunks


def _create_module_summary(
    source: SourceFile, base_path: List[str], chunks: List[RawChunk],
) -> Optional[RawChunk]:
    """Create a module-level summary chunk from file header."""
    first_code_line = min((c.line_start for c in chunks), default=len(source.lines))
    summary_end = min(20, first_code_line)

    if summary_end <= 1:
        return None

    chunk_text = "\n".join(source.lines[: summary_end])
    return RawChunk(
        text=chunk_text,
        chunk_type="module",
        name=source.path.stem,
        heading_path=base_path,
        line_start=0,
        line_end=summary_end - 1,
        semantic_depth=0,
        structural_depth=0,
    )


# ── Structural format extraction (JSON, YAML, TOML) ──────────────────────────

def _chunk_structural(
    language: str, tree: Any, source: SourceFile, base_path: List[str],
) -> List[RawChunk]:
    """Chunk structured data formats by top-level keys/sections."""
    if tree is None:
        return []

    root = tree.root_node
    chunks: List[RawChunk] = []

    if language == "json":
        chunks = _extract_json_sections(source, root, base_path)
    elif language == "yaml":
        chunks = _extract_yaml_sections(source, root, base_path)
    elif language == "toml":
        chunks = _extract_toml_sections(source, root, base_path)

    if not chunks:
        chunk_text = source.text
        chunks = [RawChunk(
            text=chunk_text,
            chunk_type="config_file",
            name=source.path.stem,
            heading_path=base_path,
            line_start=0,
            line_end=max(0, len(source.lines) - 1),
        )]

    for c in chunks:
        c.language_tier = "structural"
        c.semantic_depth = 0

    return chunks


def _extract_json_sections(
    source: SourceFile, root: Any, base_path: List[str],
) -> List[RawChunk]:
    """Extract top-level keys from a JSON object."""
    chunks: List[RawChunk] = []
    for child in root.children:
        if child.type == "object":
            for pair in child.children:
                if pair.type == "pair":
                    key_node = pair.child_by_field_name("key")
                    if key_node:
                        key_text = key_node.text.decode("utf-8").strip('"\'')
                        lo = pair.start_point[0]
                        hi = pair.end_point[0]
                        chunk_text = "\n".join(source.lines[lo : hi + 1])
                        chunks.append(RawChunk(
                            text=chunk_text,
                            chunk_type="config_section",
                            name=key_text,
                            heading_path=base_path + [key_text],
                            line_start=lo,
                            line_end=hi,
                            structural_depth=1,
                        ))
        elif child.type == "array":
            lo = child.start_point[0]
            hi = child.end_point[0]
            chunk_text = "\n".join(source.lines[lo : hi + 1])
            chunks.append(RawChunk(
                text=chunk_text,
                chunk_type="config_section",
                name="root_array",
                heading_path=base_path + ["root_array"],
                line_start=lo,
                line_end=hi,
                structural_depth=1,
            ))
    return chunks


def _extract_yaml_sections(
    source: SourceFile, root: Any, base_path: List[str],
) -> List[RawChunk]:
    """Extract top-level keys from a YAML document."""
    chunks: List[RawChunk] = []
    for child in root.children:
        if child.type == "block_mapping":
            for pair in child.children:
                _yaml_pair_to_chunk(pair, source, base_path, chunks)
        elif child.type == "block_mapping_pair":
            _yaml_pair_to_chunk(child, source, base_path, chunks)
    return chunks


def _yaml_pair_to_chunk(
    pair: Any, source: SourceFile, base_path: List[str], chunks: List[RawChunk],
) -> None:
    """Convert a YAML mapping pair to a RawChunk."""
    if pair.type != "block_mapping_pair":
        return
    key_node = pair.child_by_field_name("key")
    if key_node:
        key_text = key_node.text.decode("utf-8").strip()
        lo = pair.start_point[0]
        hi = pair.end_point[0]
        chunk_text = "\n".join(source.lines[lo : hi + 1])
        chunks.append(RawChunk(
            text=chunk_text,
            chunk_type="config_section",
            name=key_text,
            heading_path=base_path + [key_text],
            line_start=lo,
            line_end=hi,
            structural_depth=1,
        ))


def _extract_toml_sections(
    source: SourceFile, root: Any, base_path: List[str],
) -> List[RawChunk]:
    """Extract tables/sections from a TOML document."""
    chunks: List[RawChunk] = []
    for child in root.children:
        if child.type == "table":
            header = None
            for sub in child.children:
                if sub.type in ("bare_key", "dotted_key", "quoted_key"):
                    header = sub.text.decode("utf-8")
                    break
            name = header or "table"
            lo = child.start_point[0]
            hi = child.end_point[0]
            chunk_text = "\n".join(source.lines[lo : hi + 1])
            chunks.append(RawChunk(
                text=chunk_text,
                chunk_type="config_section",
                name=name,
                heading_path=base_path + [name],
                line_start=lo,
                line_end=hi,
                structural_depth=1,
            ))
        elif child.type == "pair":
            key_node = child.child_by_field_name("key")
            if key_node:
                key_text = key_node.text.decode("utf-8")
                lo = child.start_point[0]
                hi = child.end_point[0]
                chunk_text = "\n".join(source.lines[lo : hi + 1])
                chunks.append(RawChunk(
                    text=chunk_text,
                    chunk_type="config_entry",
                    name=key_text,
                    heading_path=base_path + [key_text],
                    line_start=lo,
                    line_end=hi,
                    structural_depth=1,
                ))
    return chunks


# ── Markup extraction (HTML, CSS, XML) ────────────────────────────────────────

def _chunk_markup(
    language: str, tree: Any, source: SourceFile, base_path: List[str],
) -> List[RawChunk]:
    """Chunk markup formats by semantic elements or rulesets."""
    if tree is None:
        return []

    chunks: List[RawChunk] = []

    if language == "html":
        _find_html_elements(tree.root_node, source, base_path, chunks)
    elif language == "css":
        chunks = _extract_css_rulesets(source, tree.root_node, base_path)
    elif language == "xml":
        chunks = _extract_xml_elements(source, tree.root_node, base_path)

    if not chunks:
        chunk_text = source.text
        chunks = [RawChunk(
            text=chunk_text,
            chunk_type="markup_file",
            name=source.path.stem,
            heading_path=base_path,
            line_start=0,
            line_end=max(0, len(source.lines) - 1),
        )]

    for c in chunks:
        c.language_tier = "hybrid"
        c.semantic_depth = 0

    return chunks


_SEMANTIC_HTML_TAGS = frozenset({
    "head", "header", "nav", "main", "section",
    "article", "aside", "footer", "form",
})


def _get_html_tag_name(element_node: Any) -> Optional[str]:
    """Extract tag name from an HTML element node."""
    for child in element_node.children:
        if child.type in ("start_tag", "self_closing_tag"):
            for tag_child in child.children:
                if tag_child.type == "tag_name":
                    return tag_child.text.decode("utf-8")
    return None


def _find_html_elements(
    node: Any, source: SourceFile, base_path: List[str],
    chunks: List[RawChunk], depth: int = 0,
) -> None:
    """Recursively find semantic HTML5 elements and create chunks."""
    if node.type == "element":
        tag_name = _get_html_tag_name(node)
        if tag_name and tag_name.lower() in _SEMANTIC_HTML_TAGS:
            lo = node.start_point[0]
            hi = node.end_point[0]
            label = f"<{tag_name.lower()}>"
            chunk_text = "\n".join(source.lines[lo : hi + 1])
            chunks.append(RawChunk(
                text=chunk_text,
                chunk_type="html_section",
                name=label,
                heading_path=base_path + [label],
                line_start=lo,
                line_end=hi,
                structural_depth=1,
            ))
            return  # Don't recurse into matched elements

    for child in node.children:
        _find_html_elements(child, source, base_path, chunks, depth + 1)


def _extract_css_rulesets(
    source: SourceFile, root: Any, base_path: List[str],
) -> List[RawChunk]:
    """Extract CSS rulesets and @-rules."""
    chunks: List[RawChunk] = []
    for child in root.children:
        if child.type == "rule_set":
            selectors_node = child.child_by_field_name("selectors")
            if not selectors_node:
                for sub in child.children:
                    if sub.type != "block":
                        selectors_node = sub
                        break
            selector_text = "rule"
            if selectors_node:
                selector_text = selectors_node.text.decode("utf-8").strip()
                if len(selector_text) > 60:
                    selector_text = selector_text[:57] + "..."
            lo = child.start_point[0]
            hi = child.end_point[0]
            chunk_text = "\n".join(source.lines[lo : hi + 1])
            chunks.append(RawChunk(
                text=chunk_text,
                chunk_type="css_ruleset",
                name=selector_text,
                heading_path=base_path + [selector_text],
                line_start=lo,
                line_end=hi,
                structural_depth=1,
            ))
        elif child.type in ("at_rule", "media_statement", "import_statement",
                            "charset_statement", "keyframes_statement"):
            rule_text = child.text.decode("utf-8").split("{")[0].strip()
            if len(rule_text) > 60:
                rule_text = rule_text[:57] + "..."
            lo = child.start_point[0]
            hi = child.end_point[0]
            chunk_text = "\n".join(source.lines[lo : hi + 1])
            chunks.append(RawChunk(
                text=chunk_text,
                chunk_type="css_at_rule",
                name=rule_text,
                heading_path=base_path + [rule_text],
                line_start=lo,
                line_end=hi,
                structural_depth=1,
            ))
    return chunks


def _extract_xml_elements(
    source: SourceFile, root: Any, base_path: List[str],
) -> List[RawChunk]:
    """Extract top-level XML elements."""
    chunks: List[RawChunk] = []
    for child in root.children:
        if child.type == "element":
            tag_name = _get_html_tag_name(child)
            if tag_name:
                label = f"<{tag_name}>"
                lo = child.start_point[0]
                hi = child.end_point[0]
                chunk_text = "\n".join(source.lines[lo : hi + 1])
                chunks.append(RawChunk(
                    text=chunk_text,
                    chunk_type="xml_element",
                    name=label,
                    heading_path=base_path + [label],
                    line_start=lo,
                    line_end=hi,
                    structural_depth=1,
                ))
    return chunks


# ── Fallback line chunker ─────────────────────────────────────────────────────

def _fallback_line_chunker(
    source: SourceFile,
    max_tokens: int = DEFAULT_MAX_CHUNK_TOKENS,
    overlap: int = DEFAULT_OVERLAP_LINES,
) -> List[RawChunk]:
    """
    Fallback line-window chunker when tree-sitter parsing fails.
    Creates chunks of ~max_tokens token windows with overlap.
    """
    chunks: List[RawChunk] = []
    lines = source.lines
    if not lines:
        return chunks

    cursor = 0
    chunk_idx = 0

    while cursor < len(lines):
        # Accumulate lines until token budget
        end = cursor
        tokens = 0
        while end < len(lines):
            tokens += estimate_tokens(lines[end])
            if tokens > max_tokens and end > cursor:
                break
            end += 1

        chunk_end = min(end - 1, len(lines) - 1)
        chunk_text = "\n".join(lines[cursor : chunk_end + 1])

        chunks.append(RawChunk(
            text=chunk_text,
            chunk_type="code_block",
            name=f"block_{chunk_idx}",
            heading_path=[source.path.name, f"lines {cursor + 1}-{chunk_end + 1}"],
            line_start=cursor,
            line_end=chunk_end,
            semantic_depth=0,
            structural_depth=1,
            language_tier="unknown",
        ))

        chunk_idx += 1
        next_cursor = chunk_end + 1 - overlap
        if next_cursor <= cursor:
            next_cursor = cursor + 1
        cursor = next_cursor

    return chunks


# ── Public API ────────────────────────────────────────────────────────────────

def chunk_tree_sitter(
    source: SourceFile,
    config: Optional[IngestionConfig] = None,
) -> Optional[List[RawChunk]]:
    """
    Chunk a source file using tree-sitter AST parsing.

    Returns None if tree-sitter is unavailable or language is unsupported,
    signalling the caller to fall back to prose chunking.

    Returns a list of RawChunk objects on success (possibly via fallback
    line chunker if AST parsing fails).
    """
    if config is None:
        config = IngestionConfig()

    language = source.language
    if language is None:
        return None

    # Only attempt tree-sitter for languages we have query patterns for
    tier_config = get_language_tier(language)
    strategy = tier_config["chunk_strategy"]

    # Check if tree-sitter is available
    if not _tree_sitter_available():
        logger.debug("tree-sitter not available, falling back")
        return None

    parser = _get_parser(language)
    if parser is None:
        logger.debug("No parser for language=%s, falling back", language)
        return None

    # Parse the source
    try:
        tree = parser.parse(bytes(source.text, "utf-8"))
        if tree.root_node.has_error:
            logger.debug("Parse errors for %s, using fallback", source.path.name)
            return _fallback_line_chunker(source, config.max_chunk_tokens, config.overlap_lines)
    except Exception:
        logger.debug("Parse failed for %s, using fallback", source.path.name)
        return _fallback_line_chunker(source, config.max_chunk_tokens, config.overlap_lines)

    base_path = [source.path.name]
    tier = tier_config["tier"]
    chunks: List[RawChunk] = []

    # Dispatch to tier-specific strategy
    if strategy == "hierarchical":
        imports = _extract_imports(language, tree, source, base_path)
        classes = _extract_classes(language, tree, source, base_path)
        functions = _extract_functions(language, tree, source, base_path, depth=1)
        chunks = imports + classes + functions

        summary = _create_module_summary(source, base_path, chunks)
        if summary:
            chunks.insert(0, summary)

        for c in chunks:
            c.language_tier = tier
            # For deep_semantic, semantic_depth = structural_depth
            if c.semantic_depth == 0 and c.structural_depth > 0:
                c.semantic_depth = c.structural_depth

    elif strategy == "flat":
        imports = _extract_imports(language, tree, source, base_path)
        functions = _extract_functions(language, tree, source, base_path, depth=1)
        chunks = imports + functions

        summary = _create_module_summary(source, base_path, chunks)
        if summary:
            chunks.insert(0, summary)

        for c in chunks:
            c.language_tier = tier
            c.semantic_depth = min(c.structural_depth, 1)

    elif strategy == "structural":
        chunks = _chunk_structural(language, tree, source, base_path)

    elif strategy == "markup":
        chunks = _chunk_markup(language, tree, source, base_path)

    else:
        return _fallback_line_chunker(source, config.max_chunk_tokens, config.overlap_lines)

    if not chunks:
        return _fallback_line_chunker(source, config.max_chunk_tokens, config.overlap_lines)

    return chunks
