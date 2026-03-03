"""
AIController – Manages inference loops and prompt formatting for local models.
Communicates with the Ollama API for generation and model listing.

Surgeon-Agent extensions:
  - format_prompt now accepts a `manifest` kwarg for the [FILE MANIFEST] block
  - is_holistic_query detects whole-file analysis intent
  - generate_accumulator iterates through all chunks, accumulating understanding
    before issuing the final answer
"""
import re
import requests
import threading
import json

OLLAMA_BASE = "http://localhost:11434"

# ── holistic-query detection ─────────────────────────────────────────────────
# Queries matching these patterns require whole-file reasoning (accumulator mode)
_HOLISTIC_PATTERNS = [
    re.compile(r, re.IGNORECASE) for r in [
        r"\b(explain|describe|summarize|overview|understand)\b",
        r"\bfind all\b",
        r"\bdoes this\b",
        r"\bwhere (is|are)\b",
        r"\bhow does .+ work\b",
        r"\bwhat (is|does|are)\b",
        r"\bany .+(bug|issue|problem|error|leak|vuln)\b",
        r"\blist (all|every)\b",
        r"\bwhat (could|should|would)\b",
        r"\bshow (me|all)\b",
    ]
]


class AIController:
    """
    Handles all AI inference operations.
    - Lists available local models
    - Formats prompts with context
    - Runs generation requests against Ollama
    """

    def __init__(self, log=None):
        self.log = log or (lambda msg: None)
        self._models = []

    # ── model discovery ─────────────────────────────────────

    def list_models(self):
        """Fetch available models from Ollama. Returns a list of model name strings."""
        try:
            resp = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=3)
            if resp.status_code == 200:
                self._models = [m["name"] for m in resp.json().get("models", [])]
                self.log(f"Discovered {len(self._models)} local model(s).")
            else:
                self._models = []
                self.log(f"Ollama returned status {resp.status_code}")
        except Exception as e:
            self._models = []
            self.log(f"Ollama unreachable: {e}")
        return self._models

    # ── query classification ─────────────────────────────────

    @staticmethod
    def is_holistic_query(query: str) -> bool:
        """
        Return True if the query requires whole-file reasoning (accumulator mode).
        Checked client-side so there is zero latency overhead.
        """
        return any(p.search(query) for p in _HOLISTIC_PATTERNS)

    # ── prompt formatting ───────────────────────────────────

    @staticmethod
    def format_prompt(user_message, context_chunks=None, system_prompt=None,
                      manifest: str = None):
        """
        Build a prompt string for local model consumption.

        Args:
            user_message:   The user's raw chat input.
            context_chunks: List of chunk dicts from SlidingWindow / ContextSelector.
            system_prompt:  Optional system-level instruction block.
            manifest:       Optional file manifest string (Surgeon-Agent structural map).
                            When provided it is prepended as a [FILE MANIFEST] block
                            so the model always knows the shape of the whole file.
        """
        parts = []

        if system_prompt:
            parts.append(system_prompt)

        if manifest:
            parts.append(f"[FILE MANIFEST]\n{manifest}\n[/FILE MANIFEST]")

        if context_chunks:
            context_text = "\n---\n".join(ch["content"] for ch in context_chunks)
            parts.append(f"[CONTEXT]\n{context_text}\n[/CONTEXT]")

        parts.append(user_message)
        return "\n\n".join(parts)

    # ── generation ──────────────────────────────────────────

    def generate(self, model, prompt, stream_callback=None):
        """
        Send a generation request to Ollama.
        If `stream_callback` is provided, streams tokens to it.
        Otherwise, blocks and returns the full response string.
        """
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": stream_callback is not None,
        }

        try:
            resp = requests.post(
                f"{OLLAMA_BASE}/api/generate",
                json=payload,
                stream=(stream_callback is not None),
                timeout=120,
            )
            resp.raise_for_status()
        except Exception as e:
            error_msg = f"Generation failed: {e}"
            self.log(error_msg)
            return error_msg

        if stream_callback:
            full = []
            for line in resp.iter_lines():
                if line:
                    chunk = json.loads(line)
                    token = chunk.get("response", "")
                    full.append(token)
                    stream_callback(token)
                    if chunk.get("done"):
                        break
            return "".join(full)
        else:
            data = resp.json()
            return data.get("response", "")

    def generate_accumulator(self, model: str, query: str, chunks: list,
                             manifest: str = None) -> str:
        """
        Whole-file accumulator mode (Phase 3 of the Surgeon-Agent).

        Iterates through every chunk in file order.  Each iteration feeds:
            • the current accumulated understanding
            • the next code section
            • the user's query
        into the model and uses the response as the new understanding.

        A final synthesis pass produces the actual answer to the query,
        with the model's full-file analysis behind it.

        This ensures every line of the file is "touched" before responding —
        the "never answer until the window has touched EOF" guarantee.
        """
        self.log(f"Accumulator mode: {len(chunks)} chunks × {model}")

        # Optional: prime the accumulator with the manifest as initial state
        accumulator = (
            f"[FILE MANIFEST]\n{manifest}\n[/FILE MANIFEST]"
            if manifest else "(beginning analysis)"
        )

        for i, ch in enumerate(chunks):
            s = ch.get("start_line", "?")
            e = ch.get("end_line",   "?")
            batch_prompt = (
                f"You are analysing a source file section by section.\n\n"
                f"CURRENT UNDERSTANDING:\n{accumulator}\n\n"
                f"NEW SECTION (lines {s}–{e}):\n{ch['content']}\n\n"
                f"USER QUERY: {query}\n\n"
                f"Integrate this section into your understanding. "
                f"Be concise (max 200 words). Focus on what is relevant to the query."
            )
            response = self.generate(model, batch_prompt)
            if response and not response.startswith("Generation failed:"):
                accumulator = response
            self.log(f"  Accumulator pass {i + 1}/{len(chunks)} done")

        # Final synthesis pass
        final_prompt = (
            f"You have just analysed an entire source file section by section.\n\n"
            f"YOUR FULL-FILE ANALYSIS:\n{accumulator}\n\n"
            f"USER QUERY: {query}\n\n"
            f"Give a direct, specific answer. "
            f"Cite line numbers (e.g. L42) where relevant."
        )
        return self.generate(model, final_prompt)

    def generate_async(self, model, prompt, on_token=None, on_done=None):
        """
        Run generation in a background thread.
        `on_token(str)` is called per token, `on_done(str)` with the full response.
        """
        def _run():
            result = self.generate(model, prompt, stream_callback=on_token)
            if on_done:
                on_done(result)

        threading.Thread(target=_run, daemon=True).start()

    # ── controller dispatch ─────────────────────────────────

    def handle(self, schema):
        """Controller dispatch for the BackendEngine."""
        action = schema.get("action")

        if action == "list_models":
            return {"status": "ok", "models": self.list_models()}

        elif action == "generate":
            model    = schema.get("model", "")
            prompt   = schema.get("prompt", "")
            context  = schema.get("context_chunks") or []
            manifest = schema.get("manifest") or None

            # ── Holistic query → accumulator mode ───────────
            if schema.get("holistic") or self.is_holistic_query(prompt):
                self.log("Holistic query detected — entering accumulator mode")
                result = self.generate_accumulator(model, prompt, context, manifest)
            else:
                # ── Standard query → manifest + selected chunks
                formatted = self.format_prompt(
                    prompt, context,
                    system_prompt=schema.get("system_prompt"),
                    manifest=manifest,
                )
                result = self.generate(model, formatted)

            if isinstance(result, str) and result.startswith("Generation failed:"):
                return {"status": "error", "message": result}
            return {"status": "ok", "response": result}

        return {"status": "error", "message": f"Unknown AI action: {action}"}
