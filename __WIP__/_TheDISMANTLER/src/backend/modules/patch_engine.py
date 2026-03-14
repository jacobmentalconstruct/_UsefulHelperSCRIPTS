"""
PatchEngine – Whitespace-safe patching for AI-suggested code changes.
Pure logic module with zero UI dependencies.

Provides:
- Tokenized line decomposition (leading_ws | content | trailing_ws)
- Content-only matching (indentation-immune)
- Structured patch operations (replace, insert_after, insert_before, delete)
- Context-based disambiguation for multiple matches
- Preview generation for before/after diffs
"""
import re
import difflib
from typing import Dict, List, Optional, Tuple


class TokenizedLine:
    """A line decomposed into leading whitespace, content, and trailing whitespace."""

    __slots__ = ("line_num", "raw", "leading", "content", "trailing")

    def __init__(self, line_num: int, raw: str):
        self.line_num = line_num
        self.raw = raw
        stripped = raw.rstrip()
        self.trailing = raw[len(stripped):]
        self.leading = stripped[: len(stripped) - len(stripped.lstrip())]
        self.content = stripped.lstrip()

    def matches_content(self, target: str) -> bool:
        """Match on content only, ignoring indentation."""
        return self.content == target.strip()

    def __repr__(self):
        return f"L{self.line_num}: {self.raw!r}"


class PatchEngine:
    """
    Applies structured patches to source code with indentation preservation.

    Patch format:
    {
        "op":              "replace" | "insert_after" | "insert_before" | "delete",
        "match":           "old content to find",
        "value":           "new content (for replace/insert)",
        "context_before":  "line before match (for disambiguation)",
        "context_after":   "line after match (for disambiguation)",
        "preserve_indent": true | false
    }
    """

    @staticmethod
    def tokenize(source: str) -> List[TokenizedLine]:
        """Decompose source into tokenized lines."""
        return [
            TokenizedLine(i, line)
            for i, line in enumerate(source.splitlines(), start=1)
        ]

    @staticmethod
    def apply_patch(source: str, patch: Dict) -> Tuple[str, bool]:
        """
        Apply a single patch operation to source code.

        Returns:
            (patched_source, success)
        """
        op = patch.get("op")
        match_content = patch.get("match", "").strip()
        value = patch.get("value", "")
        context_before = patch.get("context_before", "").strip()
        context_after = patch.get("context_after", "").strip()
        preserve_indent = patch.get("preserve_indent", True)

        lines = source.splitlines()
        tokens = PatchEngine.tokenize(source)

        # Find matching line(s)
        candidates = [
            t for t in tokens if t.matches_content(match_content)
        ]

        if not candidates:
            # Fuzzy fallback: try substring match
            candidates = [
                t for t in tokens if match_content in t.content
            ]

        if not candidates:
            return source, False

        # Disambiguate with context
        target = candidates[0]
        if len(candidates) > 1 and (context_before or context_after):
            for c in candidates:
                idx = c.line_num - 1
                before_ok = (
                    not context_before
                    or (idx > 0 and context_before in lines[idx - 1])
                )
                after_ok = (
                    not context_after
                    or (idx < len(lines) - 1 and context_after in lines[idx + 1])
                )
                if before_ok and after_ok:
                    target = c
                    break

        idx = target.line_num - 1  # 0-based index

        if op == "replace":
            if preserve_indent:
                new_line = target.leading + value.strip()
            else:
                new_line = value
            lines[idx] = new_line

        elif op == "insert_after":
            indent = target.leading if preserve_indent else ""
            lines.insert(idx + 1, indent + value.strip())

        elif op == "insert_before":
            indent = target.leading if preserve_indent else ""
            lines.insert(idx, indent + value.strip())

        elif op == "delete":
            lines.pop(idx)

        else:
            return source, False

        return "\n".join(lines), True

    @staticmethod
    def apply_patches(source: str, patches: List[Dict]) -> Tuple[str, List[Dict]]:
        """
        Apply multiple patches in sequence.
        Returns (final_source, list_of_results).
        """
        results = []
        current = source

        for patch in patches:
            new_source, ok = PatchEngine.apply_patch(current, patch)
            results.append({
                "op": patch.get("op"),
                "match": patch.get("match"),
                "success": ok,
            })
            if ok:
                current = new_source

        return current, results

    @staticmethod
    def preview(original: str, patched: str, context_lines: int = 3) -> str:
        """
        Generate a unified diff preview between original and patched code.
        """
        orig_lines = original.splitlines(keepends=True)
        new_lines = patched.splitlines(keepends=True)
        diff = difflib.unified_diff(
            orig_lines,
            new_lines,
            fromfile="original",
            tofile="patched",
            n=context_lines,
        )
        return "".join(diff)

    @staticmethod
    def validate_patches(patches: List[Dict]) -> Tuple[bool, List[str]]:
        """
        Validate a list of patches before applying.
        Returns (all_valid, list_of_errors).
        """
        errors = []
        valid_ops = {"replace", "insert_after", "insert_before", "delete"}

        for i, patch in enumerate(patches):
            op = patch.get("op")
            if op not in valid_ops:
                errors.append(f"Patch {i}: Invalid op '{op}'")
            if not patch.get("match"):
                errors.append(f"Patch {i}: Missing 'match' field")
            if op in ("replace", "insert_after", "insert_before") and not patch.get("value"):
                errors.append(f"Patch {i}: '{op}' requires 'value' field")

        return len(errors) == 0, errors
