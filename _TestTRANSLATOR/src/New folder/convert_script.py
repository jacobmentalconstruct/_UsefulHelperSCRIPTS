"""
Utility for converting a plain Python script into a microservice based on a
boilerplate template.  The conversion extracts import statements, helper
functions (those whose names begin with an underscore), and the remaining
execution logic from the origin script.  It then injects these pieces into a
predefined boilerplate class, placing the logic inside the ``execute`` method
and helper functions at the top of the file.

This script does not require a language model.  It demonstrates the "Mad Libs"
approach described in the project README: assemble a microservice from
components without rewriting the class structure.  To run it, provide the
origin script and the boilerplate template on the command line, for example::

    python convert_script.py origin.py _boilerplates/microservice_boiler_plate.py output.py

"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path
from typing import List, Tuple


def extract_sections(source_code: str) -> Tuple[str, str, str]:
    """
    Parse a Python source file and extract import statements, helper functions,
    and the remaining logic.

    Parameters
    ----------
    source_code : str
        The text of the origin Python file.

    Returns
    -------
    tuple[str, str, str]
        A tuple containing three strings: ``imports``, ``helpers`` and
        ``logic``.  Each string preserves the original formatting except
        indentation adjustments for the logic section.
    """
    lines = source_code.splitlines()
    imports: List[str] = []
    helpers: List[str] = []
    logic: List[str] = []

    # Use AST to identify top‑level helper functions and their line numbers
    try:
        tree = ast.parse(source_code)
        helper_spans: List[Tuple[int, int]] = []
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                # Record import lines by line numbers (1‑based) so we can skip
                # them later when constructing the logic section
                imports.append("\n".join(lines[node.lineno - 1 : node.end_lineno]))
            elif isinstance(node, ast.FunctionDef) and node.name.startswith("_"):
                # Capture helper function source lines
                helper_spans.append((node.lineno - 1, node.end_lineno))
        # Merge helper spans to avoid duplicates
        helper_lines: List[str] = []
        for start, end in helper_spans:
            helper_lines.extend(lines[start:end])
        helpers = helper_lines

        # Determine which line numbers belong to imports, helpers and the module
        # docstring to exclude.  The docstring, if present, is represented as
        # the first statement in the module body that is an Expr whose value is
        # a Constant string.  We derive its span via lineno/end_lineno.
        excluded: set[int] = set()
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                excluded.update(range(node.lineno - 1, node.end_lineno))
        for start, end in helper_spans:
            excluded.update(range(start, end))
        # Exclude module docstring lines
        if (
            tree.body
            and isinstance(tree.body[0], ast.Expr)
            and isinstance(getattr(tree.body[0], "value", None), ast.Constant)
            and isinstance(tree.body[0].value.value, str)
        ):
            doc_node = tree.body[0]
            excluded.update(range(doc_node.lineno - 1, doc_node.end_lineno))
        # Everything else (except excluded lines) goes into logic
        for idx, line in enumerate(lines):
            if idx in excluded:
                continue
            logic.append(line)
    except Exception:
        # Fallback: naive extraction – take lines starting with 'import' as imports
        for line in lines:
            if line.startswith("import ") or line.startswith("from "):
                imports.append(line)
            elif line.lstrip().startswith("def _"):
                helpers.append(line)
            else:
                logic.append(line)
    # Deduplicate import lines and join helpers
    import_block = "\n".join(imports)
    helpers_block = "\n".join(helpers).rstrip()
    logic_block = "\n".join(logic).rstrip()
    return import_block, helpers_block, logic_block


def indent_logic(logic: str, indent: int = 8) -> str:
    """Indent every line of the logic block by a fixed number of spaces."""
    indentation = " " * indent
    if not logic:
        return ""  # nothing to indent
    return "\n".join(f"{indentation}{line}" if line.strip() != "" else "" for line in logic.splitlines())


def assemble_microservice(
    imports: str,
    helpers: str,
    logic: str,
    boilerplate: str,
) -> str:
    """
    Assemble the final microservice code by combining imports, boilerplate,
    helpers, and logic.  Logic is injected into the location marked with
    ``# [INJECT LOGIC HERE]``.  Helpers are inserted just before the first
    class definition in the boilerplate.  Imports appear at the very top.
    """
    # Prepend imports
    final_code = f"{imports}\n\n{boilerplate}" if imports else boilerplate
    # Insert logic
    indented_logic = indent_logic(logic)
    if "# [INJECT LOGIC HERE]" in final_code:
        final_code = final_code.replace("# [INJECT LOGIC HERE]", indented_logic or "        pass")
    else:
        final_code += f"\n\n# ORPHANED LOGIC:\n{indented_logic}"
    # Insert helpers
    if helpers and "class " in final_code:
        parts = final_code.split("class ", 1)
        final_code = f"{parts[0]}\n\n# --- HELPERS ---\n{helpers}\n\nclass {parts[1]}"
    elif helpers:
        final_code += f"\n\n{helpers}"
    return final_code


def main(argv: List[str]) -> None:
    if len(argv) != 3:
        print(
            "Usage: python convert_script.py <origin.py> <boilerplate.py> <output.py>",
            file=sys.stderr,
        )
        sys.exit(1)
    origin_path, boiler_path, output_path = argv
    origin_code = Path(origin_path).read_text(encoding="utf-8", errors="ignore")
    boiler_code = Path(boiler_path).read_text(encoding="utf-8", errors="ignore")
    imports, helpers, logic = extract_sections(origin_code)
    final_code = assemble_microservice(imports, helpers, logic, boiler_code)
    Path(output_path).write_text(final_code, encoding="utf-8")
    print(f"Converted {origin_path} -> {output_path}")


if __name__ == "__main__":
    main(sys.argv[1:])