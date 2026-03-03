"""
ContextSelector – Intent-driven chunk selection for the Surgeon-Agent architecture.

Replaces the naive cursor-proximity ranking with a scored selection that weights:
  1. Query token overlap with chunk name   (strongest signal — 3×)
  2. Query token overlap with chunk content (broad signal — 0.4×)
  3. Cursor proximity                       (tiebreaker / edit context — bonus)

The top-1 chunk is always included regardless of score (safety net for inline edits).
Remaining budget is filled in score order, highest first.
"""
import re

# Default token budget — 4× the old default (2048) to support richer context.
DEFAULT_BUDGET = 8192

# Stop-words excluded from query token matching (common English + Python keywords)
_STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "to", "of", "in",
    "for", "on", "with", "as", "at", "by", "from", "or", "and", "but",
    "not", "this", "that", "it", "its", "my", "our", "your", "their",
    # Python/code noise words
    "def", "class", "return", "import", "from", "pass", "self", "true", "false",
    "none", "if", "else", "elif", "for", "while", "try", "except", "with",
    "print", "get", "set", "run", "call",
}

# Proximity bonus decay: 1 / (1 + dist/DECAY).
# At DECAY=50: a chunk 50 lines away gets 0.5; 200 lines = 0.2.
_PROXIMITY_DECAY = 50.0


def _tokenize(text: str) -> list:
    """Split text into lowercase alpha-numeric tokens, dropping stop-words."""
    tokens = re.findall(r"[a-zA-Z_]\w*", text.lower())
    return [t for t in tokens if t not in _STOP_WORDS and len(t) > 1]


class ContextSelector:
    """
    Scores and selects chunks for a given query string.
    Stateless — all methods are static.
    """

    @staticmethod
    def score_and_select(
        query: str,
        chunks: list,
        cursor_line: int = 1,
        budget: int = DEFAULT_BUDGET,
    ) -> list:
        """
        Select the best chunks for the query within the token budget.

        Args:
            query:       The user's chat message.
            chunks:      List of chunk dicts from SlidingWindow (must have
                         name, content, start_line, end_line, token_est).
            cursor_line: Current editor cursor (1-based line number).
            budget:      Max total token_est to include.

        Returns:
            List of chunk dicts, sorted by start_line (file order).
        """
        if not chunks:
            return []

        query_tokens = _tokenize(query)

        scored = []
        for ch in chunks:
            score = ContextSelector._score(ch, query_tokens, cursor_line)
            scored.append((score, ch))

        # Sort descending by score
        scored.sort(key=lambda x: x[0], reverse=True)

        # Always include the top-scored chunk (nearest-to-intent safety net)
        selected = []
        spent    = 0
        for i, (score, ch) in enumerate(scored):
            est = ch.get("token_est", 1)
            if spent + est > budget:
                if i == 0:
                    # Force-include top chunk; trim if huge
                    entry = dict(ch)
                    if est > budget:
                        char_budget      = budget * 4
                        entry["content"] = entry["content"][:char_budget]
                        entry["token_est"] = budget
                        entry["trimmed"] = True
                    selected.append(entry)
                    spent += entry["token_est"]
                continue
            spent += est
            selected.append(dict(ch))

        # Return in file order so the model reads code top-to-bottom
        selected.sort(key=lambda c: c.get("start_line", 0))
        return selected

    @staticmethod
    def _score(chunk: dict, query_tokens: list, cursor_line: int) -> float:
        """Compute a relevance score for one chunk against the query tokens."""
        if not query_tokens:
            # No query signal — fall back to pure cursor proximity
            dist = abs(chunk.get("start_line", 1) - cursor_line)
            return 1.0 / (1.0 + dist / _PROXIMITY_DECAY)

        name_text    = (chunk.get("name") or "").lower()
        content_text = (chunk.get("content") or "").lower()

        name_score    = sum(1 for t in query_tokens if t in name_text) * 3.0
        content_score = sum(1 for t in query_tokens if t in content_text) * 0.4

        mid = (chunk.get("start_line", 1) + chunk.get("end_line", 1)) / 2
        dist = abs(mid - cursor_line)
        proximity_bonus = 1.0 / (1.0 + dist / _PROXIMITY_DECAY)

        return name_score + content_score + proximity_bonus
