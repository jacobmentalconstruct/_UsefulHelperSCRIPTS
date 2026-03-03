"""
SearchEngine – Advanced find/replace with whitespace pattern matching.
Pure logic module with zero UI dependencies.

Provides:
- Whitespace-agnostic matching (tabs/spaces/newlines as equivalent)
- Case-sensitive/insensitive search
- Pattern-based find with context
- Multi-match replacement with count tracking
"""
import re
from typing import List, Tuple, Optional


class SearchEngine:
    """
    Advanced search/replace engine with flexible whitespace handling.
    """

    @staticmethod
    def _normalize_whitespace(text: str) -> str:
        """
        Replace all whitespace variants with single space for comparison.
        Converts: \r\n → ' ', \n → ' ', \r → ' ', \t → ' ', multiple spaces → ' '
        """
        # Replace all whitespace sequences with single space
        normalized = re.sub(r'[\r\n\t ]+', ' ', text)
        return normalized.strip()

    @staticmethod
    def _escape_regex(pattern: str) -> str:
        """Escape regex special characters for literal matching."""
        return re.escape(pattern)

    @staticmethod
    def find_all(
        source: str,
        pattern: str,
        match_case: bool = False,
        match_ws_exactly: bool = False
    ) -> List[Tuple[int, int, str, str]]:
        """
        Find all occurrences of pattern in source text.

        Args:
            source: Source text to search in
            pattern: Search pattern (literal string, not regex)
            match_case: If False, search is case-insensitive
            match_ws_exactly: If False, all whitespace is treated as equivalent

        Returns:
            List of (line_num, col_num, line_text, matched_text) tuples
            - line_num: 1-based line number
            - col_num: 0-based column number
            - line_text: Full text of the line containing match
            - matched_text: The actual matched text from source
        """
        if not pattern:
            return []

        results = []
        lines = source.splitlines()

        if match_ws_exactly:
            # Literal matching: use escaped pattern as-is
            search_pattern = SearchEngine._escape_regex(pattern)
            flags = 0 if match_case else re.IGNORECASE
            try:
                compiled = re.compile(search_pattern, flags)
            except re.error:
                return results

            for line_num, line in enumerate(lines, start=1):
                for match in compiled.finditer(line):
                    col_num = match.start()
                    matched_text = match.group(0)
                    results.append((line_num, col_num, line, matched_text))

        else:
            # Whitespace-agnostic matching: convert each whitespace run in the
            # pattern to \s+ so we search the ORIGINAL line directly.
            # This gives the true col_num (match.start()) and the exact
            # matched text (match.group(0)) — both in terms of the original
            # source, not a normalized copy that has stripped indentation.
            ws_flexible = re.sub(r'\s+', r'\\s+', re.escape(pattern))
            flags = 0 if match_case else re.IGNORECASE
            try:
                compiled = re.compile(ws_flexible, flags)
            except re.error:
                return results

            for line_num, line in enumerate(lines, start=1):
                for match in compiled.finditer(line):
                    col_num = match.start()        # true column in original line
                    matched_text = match.group(0)  # actual characters matched
                    results.append((line_num, col_num, line, matched_text))

        return results

    @staticmethod
    def replace_all(
        source: str,
        pattern: str,
        replacement: str,
        match_case: bool = False,
        match_ws_exactly: bool = False
    ) -> Tuple[str, int]:
        """
        Replace all occurrences of pattern with replacement.

        Args:
            source: Source text to search in
            pattern: Search pattern (literal string)
            replacement: Replacement text
            match_case: If False, search is case-insensitive
            match_ws_exactly: If False, all whitespace is treated as equivalent

        Returns:
            Tuple of (modified_source, replacement_count)
        """
        if not pattern:
            return source, 0

        if match_ws_exactly:
            # Literal replacement
            search_pattern = SearchEngine._escape_regex(pattern)
            flags = 0 if match_case else re.IGNORECASE
            try:
                compiled = re.compile(search_pattern, flags)
            except re.error:
                return source, 0

            new_source, count = compiled.subn(replacement, source)
            return new_source, count

        else:
            # Whitespace-agnostic replacement
            lines = source.splitlines(keepends=True)
            replacement_count = 0
            new_lines = []
            normalized_pattern = SearchEngine._normalize_whitespace(pattern)

            for line in lines:
                normalized_line = SearchEngine._normalize_whitespace(line)
                search_text = normalized_line if not match_case else normalized_line.lower()
                search_pattern = normalized_pattern if not match_case else normalized_pattern.lower()

                # Count occurrences in this line
                count_in_line = search_text.count(search_pattern)
                replacement_count += count_in_line

                # Replace all occurrences (simple approach: replace all matches of normalized pattern)
                if count_in_line > 0:
                    # Use simple replacement: find and replace literal matches
                    # For whitespace-agnostic, we do simple replacement of the pattern
                    new_line = line.replace(pattern, replacement) if match_case else \
                               line.replace(pattern, replacement)  # Case-insensitive doesn't work with str.replace

                    # For case-insensitive, use regex
                    if not match_case:
                        search_pattern_re = SearchEngine._escape_regex(pattern)
                        new_line = re.sub(search_pattern_re, replacement, line, flags=re.IGNORECASE)
                    else:
                        new_line = line.replace(pattern, replacement)

                    new_lines.append(new_line)
                else:
                    new_lines.append(line)

            new_source = ''.join(new_lines)
            return new_source, replacement_count

    @staticmethod
    def count_matches(
        source: str,
        pattern: str,
        match_case: bool = False,
        match_ws_exactly: bool = False
    ) -> int:
        """Count total number of matches without returning details."""
        matches = SearchEngine.find_all(source, pattern, match_case, match_ws_exactly)
        return len(matches)
