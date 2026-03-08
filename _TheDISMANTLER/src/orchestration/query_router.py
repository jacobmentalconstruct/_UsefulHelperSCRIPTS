"""
QueryRouter – Pipeline orchestration for the Warm Constrained Swarm.

Implements the 7-step execution pipeline:

  1. User submits a query
  2. Context Engine generates the Manifest
  3. Swarm Orchestrator sends Manifest + Query to the Scout
  4. Scout returns targeted chunk IDs
  5. Context Engine fetches specified chunks and prepends absolute line numbers
  6. Swarm Orchestrator sends Anchored Chunks + Query to the Surgeon
  7. Surgeon returns the final, line-accurate response to the UI

This module contains ZERO database logic and ZERO HTTP logic.
It only orchestrates hand-offs between ContextBuilder and SwarmClient.

Dependencies:
  - db.context_builder.ContextBuilder   (data layer)
  - llm.swarm_client.SwarmClient        (inference layer)
"""

import json
import re

from db.context_builder import ContextBuilder
from llm.swarm_client import SwarmClient


# ── Intent Classifier patterns ────────────────────────────────
# Heuristic keyword matching for pre-flight intent classification.
# Order matters: first match wins.
_INTENT_PATTERNS = {
    "bug_hunt": re.compile(
        r"\b(bug|error|issue|fix|fail|crash|wrong|broken|exception|traceback|raise)\b",
        re.IGNORECASE,
    ),
    "refactor": re.compile(
        r"\b(refactor|clean|simplify|improve|optimize|rename|extract|restructure|rewrite)\b",
        re.IGNORECASE,
    ),
    "structural_analysis": re.compile(
        r"\b(explain|describe|summarize|overview|understand|how does|architecture|structure|walk me through)\b",
        re.IGNORECASE,
    ),
}

_FILE_WIDE_PATTERN = re.compile(
    r"\b(entire|whole|all|every|file|codebase|throughout|global)\b",
    re.IGNORECASE,
)


# ── Scout prompt template ─────────────────────────────────────
# The Scout receives the structural manifest and the user query.
# It must return ONLY a JSON array of chunk_id integers.
_SCOUT_PROMPT_TEMPLATE = """\
You are a code triage assistant. Your ONLY job is to select which code \
sections are relevant to the user's query.

Below is the structural map of a source file, followed by a chunk index \
listing every code section with its ID, name, type, and line range.

{manifest}

CHUNK INDEX:
{chunk_index}

USER QUERY: {query}

Respond with ONLY a JSON array of chunk_id integers that are relevant \
to answering the query. Select the minimum set needed — prefer precision \
over recall. Example response: [3, 7, 12]

If the query is about the whole file or is very broad, return all chunk IDs.
If unsure, include the chunk. Never return an empty array.

JSON array:"""

# ── Surgeon prompt template ───────────────────────────────────
# The Surgeon receives the manifest, spatially-anchored chunks, and query.
_SURGEON_PROMPT_TEMPLATE = """\
You are a precise code analyst. Every line of code below has its absolute \
line number prepended (e.g. "66: def load_file"). When referencing code in \
your response, ALWAYS cite the exact line numbers you see (e.g. L66, L66-71).

{manifest_block}

{context_block}

USER QUERY: {query}

Provide a direct, specific answer. Cite line numbers where relevant."""


class QueryRouter:
    """
    Stateless pipeline orchestrator.

    Connects ContextBuilder (data) → SwarmClient (inference) without
    owning any state itself. Each route() call is an independent pipeline
    execution — no cross-query memory.
    """

    def __init__(self, swarm: SwarmClient = None, log=None, db_path: str = None):
        """
        Args:
            swarm:   A SwarmClient instance. Created with defaults if None.
            log:     Optional logging callback (str -> None).
            db_path: Optional SQLite database path override for ContextBuilder.
        """
        self.swarm = swarm or SwarmClient(log=log)
        self.log = log or (lambda msg: None)
        self.db_path = db_path

    # ── Intent Classification ──────────────────────────────────

    def classify_intent(self, query: str, file_name: str = None) -> dict:
        """
        Pre-flight heuristic intent classification.

        Produces a structured IntentResult dict that drives the Surgeon's
        system prompt (identity anchor) and provides telemetry labels.

        Args:
            query:     The user's chat message.
            file_name: Basename of the open file (e.g. "datastore.py").

        Returns:
            {
                "intent":   "structural_analysis" | "bug_hunt" | "refactor" | "general",
                "focus":    "file_wide" | "local_chunk",
                "persona":  str,   # Ollama system field — Surgeon's identity
                "strategy": "scout_triage",
            }
        """
        intent = next(
            (name for name, pat in _INTENT_PATTERNS.items() if pat.search(query)),
            "general",
        )
        focus = "file_wide" if _FILE_WIDE_PATTERN.search(query) else "local_chunk"

        fn = file_name or "(unknown file)"
        persona = (
            f"You are an expert code analyst and software architect. "
            f"You are examining the source file '{fn}'. "
            f"When referencing code, always cite exact line numbers (e.g. L42, L66-71)."
        )

        return {
            "intent":   intent,
            "focus":    focus,
            "persona":  persona,
            "strategy": "scout_triage",
        }

    # ── Main Pipeline ─────────────────────────────────────────

    def route(self, file_path: str, query: str, stream_callback=None,
              file_name: str = None, telemetry_callback=None) -> dict:
        """
        Execute the full Scout → Surgeon pipeline for a user query.

        Steps:
          1. Fetch manifest from DB (or build dynamically)
          2. Fetch chunk index (metadata without content)
          3. Send manifest + chunk index + query to Scout
          4. Parse Scout response → chunk IDs
          5. Fetch those chunks and apply spatial anchoring
          6. Send manifest + anchored chunks + query to Surgeon
          7. Return Surgeon response

        Args:
            file_path:       Absolute path to the open source file.
            query:           The user's chat message.
            stream_callback: Optional callback(str) for streaming Surgeon
                             tokens to the UI in real time.

        Returns:
            {
                "status":   "ok" | "error",
                "response": str,            # Surgeon's final answer
                "chunks_selected": [int],   # chunk_ids the Scout picked
                "manifest_len": int,        # chars in the manifest
            }
        """
        _tel = telemetry_callback or (lambda m: None)

        # ── Pre-flight: classify intent ───────────────────────
        intent = self.classify_intent(query, file_name)
        _tel(f"INTENT: {intent['intent']} / {intent['focus']}")
        self.log(f"Pipeline start: [{intent['intent']}] {query[:60]}...")

        # ── Step 1: Get manifest ──────────────────────────────
        manifest = ContextBuilder.get_manifest(file_path, self.db_path)
        if not manifest:
            # Fall back to dynamic generation from chunks table
            manifest = ContextBuilder.build_manifest_from_db(file_path, self.db_path)
        self.log(f"  Manifest: {len(manifest)} chars")

        # ── Step 2: Get chunk index (metadata only) ───────────
        chunk_index = ContextBuilder.get_chunk_index(file_path, self.db_path)
        if not chunk_index:
            self.log("  No chunks indexed — aborting pipeline")
            return {
                "status": "error",
                "response": "File has not been curated yet. Please curate the file first.",
                "chunks_selected": [],
                "manifest_len": len(manifest),
            }
        self.log(f"  Chunk index: {len(chunk_index)} entries")

        # ── Step 3: Scout triage ──────────────────────────────
        _tel(f"SCOUT: Triaging {len(chunk_index)} chunk(s)…")
        scout_prompt = self._build_scout_prompt(manifest, chunk_index, query)
        scout_response = self.swarm.scout(scout_prompt)
        self.log(f"  Scout raw response: {scout_response[:200]}")

        # ── Step 4: Parse Scout → chunk IDs ───────────────────
        selected_ids = self._parse_scout_response(scout_response, chunk_index)
        self.log(f"  Scout selected {len(selected_ids)} chunk(s): {selected_ids}")
        _tel(f"SCOUT: Selected {len(selected_ids)} chunk(s)")

        # ── Step 5: Fetch + anchor selected chunks ────────────
        selected_chunks = ContextBuilder.get_chunks_by_ids(selected_ids, self.db_path)
        if not selected_chunks:
            # Safety net: if Scout returned garbage, fall back to all chunks
            self.log("  WARNING: Scout selection yielded no chunks — using all")
            selected_chunks = ContextBuilder.get_all_chunks(file_path, self.db_path)
            selected_ids = [ch["chunk_id"] for ch in selected_chunks]

        self.log(f"  Fetched {len(selected_chunks)} chunk(s), applying spatial anchoring")

        # ── Step 6: Surgeon analysis ──────────────────────────
        _tel("SURGEON: Analyzing selected chunks…")
        surgeon_prompt = self._build_surgeon_prompt(manifest, selected_chunks, query)
        surgeon_response = self.swarm.surgeon(
            surgeon_prompt,
            stream_callback=stream_callback,
            system_prompt=intent["persona"],
        )
        self.log(f"  Surgeon responded: {len(surgeon_response)} chars")
        _tel(f"SURGEON: Done ({len(surgeon_response)} chars)")

        # ── Step 7: Return ────────────────────────────────────
        if surgeon_response.startswith("ERROR:"):
            return {
                "status": "error",
                "response": surgeon_response,
                "chunks_selected": selected_ids,
                "manifest_len": len(manifest),
            }

        return {
            "status": "ok",
            "response": surgeon_response,
            "chunks_selected": selected_ids,
            "manifest_len": len(manifest),
        }

    # ── Direct Surgeon (bypass Scout) ─────────────────────────

    def route_direct(self, file_path: str, query: str,
                     chunk_ids: list = None, stream_callback=None) -> dict:
        """
        Send chunks directly to the Surgeon, bypassing Scout triage.

        Useful when the caller already knows which chunks are relevant
        (e.g. from ContextSelector scoring or user-specified selection).

        If chunk_ids is None, all chunks for the file are used.

        Args:
            file_path:       Absolute path to the source file.
            query:           The user's chat message.
            chunk_ids:       Optional list of chunk_id ints to use.
            stream_callback: Optional streaming callback.

        Returns:
            Same dict structure as route().
        """
        manifest = ContextBuilder.get_manifest(file_path, self.db_path)
        if not manifest:
            manifest = ContextBuilder.build_manifest_from_db(file_path, self.db_path)

        if chunk_ids:
            chunks = ContextBuilder.get_chunks_by_ids(chunk_ids, self.db_path)
        else:
            chunks = ContextBuilder.get_all_chunks(file_path, self.db_path)

        if not chunks:
            return {
                "status": "error",
                "response": "No chunks available for this file.",
                "chunks_selected": [],
                "manifest_len": len(manifest),
            }

        surgeon_prompt = self._build_surgeon_prompt(manifest, chunks, query)
        response = self.swarm.surgeon(surgeon_prompt, stream_callback=stream_callback)

        selected_ids = [ch["chunk_id"] for ch in chunks]
        status = "error" if response.startswith("ERROR:") else "ok"

        return {
            "status": status,
            "response": response,
            "chunks_selected": selected_ids,
            "manifest_len": len(manifest),
        }

    # ── Prompt Construction ───────────────────────────────────

    @staticmethod
    def _build_scout_prompt(manifest: str, chunk_index: list, query: str) -> str:
        """
        Build the Scout's triage prompt with enriched chunk metadata.

        Each chunk entry now includes (when available):
          - Decorators (@staticmethod, @property, etc.)
          - Function signature (parameter names + types)
          - Return type
          - Call targets (what this function calls)
          - Exception types it can raise
          - Reference count (how many other chunks reference it)

        This gives the Scout dramatically better triage signals
        while still fitting in 512 tokens (no code content included).
        """
        index_lines = []
        for ch in chunk_index:
            kind = ch.get("chunk_type", "code")
            name = ch.get("name") or "(anonymous)"
            s = ch["start_line"]
            e = ch["end_line"]
            tokens = ch.get("token_est", 0)

            # Core line
            line = f"  ID={ch['chunk_id']}  [{kind}]  {name}"

            # Signature (compact)
            sig = ch.get("signature", "")
            ret = ch.get("return_type", "")
            if sig and kind in ("function", "method", "def", "async"):
                # Truncate long sigs for the Scout's tight budget
                sig_short = sig if len(sig) <= 40 else sig[:37] + "..."
                line += f"({sig_short})"
            if ret:
                line += f" \u2192 {ret}"

            line += f"  L{s}-{e}"

            # Reference count (gravity indicator)
            rc = ch.get("ref_count", 0)
            if rc > 0:
                line += f"  refs={rc}"

            # Decorators (compact)
            decorators = ch.get("decorators", [])
            if decorators:
                line += "  " + " ".join(f"@{d}" for d in decorators[:3])

            # Call targets (compact — only names)
            calls = ch.get("calls", [])
            if calls:
                call_display = calls[:5]
                suffix = f"+{len(calls)-5}" if len(calls) > 5 else ""
                line += f"  calls:[{','.join(call_display)}{suffix}]"

            # Raises
            raises = ch.get("raises", [])
            if raises:
                line += f"  raises:[{','.join(raises)}]"

            line += f"  (~{tokens}tok)"
            index_lines.append(line)

        chunk_index_str = "\n".join(index_lines)

        return _SCOUT_PROMPT_TEMPLATE.format(
            manifest=manifest,
            chunk_index=chunk_index_str,
            query=query,
        )

    @staticmethod
    def _build_surgeon_prompt(manifest: str, chunks: list, query: str) -> str:
        """
        Build the Surgeon's analysis prompt with spatially-anchored chunks.

        The manifest is wrapped in [FILE MANIFEST] tags.
        Chunks are anchored (line numbers prepended) and wrapped in [CONTEXT] tags.
        """
        manifest_block = ""
        if manifest:
            manifest_block = f"[FILE MANIFEST]\n{manifest}\n[/FILE MANIFEST]"

        context_block = ContextBuilder.format_context_block(chunks, anchored=True)

        return _SURGEON_PROMPT_TEMPLATE.format(
            manifest_block=manifest_block,
            context_block=context_block,
            query=query,
        )

    # ── Scout Response Parsing ────────────────────────────────

    @staticmethod
    def _parse_scout_response(response: str, chunk_index: list) -> list:
        """
        Extract chunk IDs from the Scout's response.

        The Scout is instructed to return a JSON array like [3, 7, 12].
        But small models can be unreliable, so we try multiple strategies:

          1. Direct JSON parse of the full response
          2. Regex extraction of a JSON array from mixed text
          3. Regex extraction of bare integers from the response

        All extracted IDs are validated against the actual chunk index.
        If parsing fails entirely, returns ALL chunk IDs (safe fallback).

        Args:
            response:    Raw string from Scout model.
            chunk_index: List of chunk metadata dicts (for ID validation).

        Returns:
            List of valid chunk_id integers.
        """
        valid_ids = {ch["chunk_id"] for ch in chunk_index}

        # Strategy 1: Direct JSON parse
        try:
            parsed = json.loads(response.strip())
            if isinstance(parsed, list):
                ids = [int(x) for x in parsed if isinstance(x, (int, float))]
                filtered = [i for i in ids if i in valid_ids]
                if filtered:
                    return filtered
        except (json.JSONDecodeError, ValueError):
            pass

        # Strategy 2: Find a JSON array embedded in text
        array_match = re.search(r'\[[\d,\s]+\]', response)
        if array_match:
            try:
                parsed = json.loads(array_match.group())
                ids = [int(x) for x in parsed if isinstance(x, (int, float))]
                filtered = [i for i in ids if i in valid_ids]
                if filtered:
                    return filtered
            except (json.JSONDecodeError, ValueError):
                pass

        # Strategy 3: Extract any bare integers from the response
        bare_ints = re.findall(r'\b(\d+)\b', response)
        if bare_ints:
            ids = [int(x) for x in bare_ints]
            filtered = [i for i in ids if i in valid_ids]
            if filtered:
                return filtered

        # Fallback: return all chunk IDs (safe — Surgeon handles the budget)
        return [ch["chunk_id"] for ch in chunk_index]
