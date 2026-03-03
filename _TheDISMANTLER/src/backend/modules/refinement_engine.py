"""
RefinementEngine – AI-assisted iterative refinement of extraction plans.
Manages refinement sessions as an in-memory state machine.
Each session tracks a plan through multiple AI inference passes,
with phase-aware prompting that shifts focus per pass.
Zero UI dependencies.
"""
import os
import uuid
from datetime import datetime


class RefinementSession:
    """
    Tracks the state of a single refinement run.
    Statuses: ready -> running -> paused -> running -> ... -> complete | cancelled
    """

    def __init__(self, file_path, initial_plan, model, max_passes=5):
        self.session_id = uuid.uuid4().hex[:8]
        self.file_path = file_path
        self.model = model
        self.max_passes = max_passes
        self.current_pass = 0
        self.initial_plan = initial_plan
        self.current_plan = initial_plan
        self.history = []       # list of PassResult dicts
        self.status = "ready"   # ready | running | paused | complete | cancelled


class RefinementEngine:
    """
    Orchestrates AI-assisted iterative refinement of extraction plans.
    Pure logic module — zero UI dependencies.

    Requires references to AIController (for inference) and
    SlidingWindow (for file context). These are injected at init.
    """

    def __init__(self, ai_controller, sliding_window, log=None):
        self.ai = ai_controller
        self.sliding_window = sliding_window
        self.log = log or (lambda msg: None)
        self._sessions = {}

    # ── session lifecycle ──────────────────────────────────

    def create_session(self, file_path, initial_plan, model, max_passes=5):
        """Create a new refinement session. Returns session_id."""
        session = RefinementSession(file_path, initial_plan, model, max_passes)
        self._sessions[session.session_id] = session
        self.log(f"Refinement session {session.session_id} created "
                 f"({max_passes} passes, model={model})")
        return session.session_id

    def get_session(self, session_id):
        """Return session state as a serializable dict."""
        s = self._sessions.get(session_id)
        if not s:
            return None
        return {
            "session_id": s.session_id,
            "file_path": s.file_path,
            "model": s.model,
            "max_passes": s.max_passes,
            "current_pass": s.current_pass,
            "status": s.status,
            "current_plan": s.current_plan,
            "history": s.history,
        }

    def cancel_session(self, session_id):
        """Cancel a session. Idempotent."""
        s = self._sessions.get(session_id)
        if s:
            s.status = "cancelled"
            self.log(f"Refinement session {session_id} cancelled")

    # ── pass execution ─────────────────────────────────────

    def execute_pass(self, session_id, stream_callback=None):
        """
        Execute a single refinement pass (blocking).
        Call from a background thread when streaming.

        stream_callback(token: str) is invoked per token for live display.
        Returns a PassResult dict.
        """
        s = self._sessions.get(session_id)
        if not s:
            return {"error": "Session not found"}
        if s.status == "cancelled":
            return {"error": "Session was cancelled"}
        if s.current_pass >= s.max_passes:
            return {"error": "All passes already completed"}

        s.status = "running"
        s.current_pass += 1
        pass_number = s.current_pass

        self.log(f"Pass {pass_number}/{s.max_passes}: building prompt...")
        prompt = self._build_prompt(s, pass_number)

        self.log(f"Pass {pass_number}/{s.max_passes}: generating...")
        result_text = self.ai.generate(
            s.model, prompt, stream_callback=stream_callback
        )

        # Record the pass
        pass_result = {
            "pass_number": pass_number,
            "input_plan": s.current_plan,
            "output_plan": result_text,
            "model": s.model,
            "token_count_est": len(result_text.split()),
            "timestamp": datetime.now().isoformat(),
        }
        s.history.append(pass_result)
        s.current_plan = result_text

        # Update status
        if pass_number >= s.max_passes:
            s.status = "complete"
            self.log(f"Refinement session {session_id} complete after {pass_number} passes")
        else:
            s.status = "paused"
            self.log(f"Pass {pass_number}/{s.max_passes} done. Awaiting approval.")

        return pass_result

    def retry_pass(self, session_id, stream_callback=None):
        """
        Re-run the most recent pass.
        Reverts the plan to pre-pass state and re-executes.
        """
        s = self._sessions.get(session_id)
        if not s:
            return {"error": "Session not found"}
        if not s.history:
            return {"error": "No passes to retry"}

        # Revert
        last = s.history.pop()
        s.current_plan = last["input_plan"]
        s.current_pass -= 1
        self.log(f"Retrying pass {s.current_pass + 1} for session {session_id}")

        return self.execute_pass(session_id, stream_callback)

    # ── prompt construction ────────────────────────────────

    def _build_prompt(self, session, pass_number):
        """
        Assemble the full prompt for a refinement pass.
        Structure:
          [system prompt — phase-aware]
          [SOURCE_FILE]...[/SOURCE_FILE]
          [CONTEXT]...[/CONTEXT]           (sliding window chunks)
          [REFINEMENT_HISTORY]...[/...]    (if passes > 1)
          [CURRENT_PLAN]...[/CURRENT_PLAN]
          Final instruction
        """
        parts = []

        # 1. System prompt (phase-aware)
        parts.append(self._system_prompt(pass_number, session.max_passes))

        # 2. Source file content
        source = self._read_file(session.file_path)
        if source:
            # Truncate very large files to keep within model context
            lines = source.splitlines()
            if len(lines) > 500:
                truncated = "\n".join(lines[:500])
                parts.append(
                    f"[SOURCE_FILE]\n{truncated}\n"
                    f"... (truncated, {len(lines)} total lines)\n[/SOURCE_FILE]"
                )
            else:
                parts.append(f"[SOURCE_FILE]\n{source}\n[/SOURCE_FILE]")

        # 3. Sliding window context (related code from the project)
        # Anchor at the midpoint of the file for broader coverage
        mid_line = max(1, len(source.splitlines()) // 2) if source else 1
        context_chunks = self.sliding_window.get_context(
            session.file_path, cursor_line=mid_line, budget=2048
        )
        if context_chunks:
            ctx_text = "\n---\n".join(ch["content"] for ch in context_chunks)
            parts.append(f"[CONTEXT]\n{ctx_text}\n[/CONTEXT]")

        # 4. Refinement history (brief, for passes > 1)
        if session.history:
            history_lines = []
            for h in session.history:
                history_lines.append(
                    f"--- Pass {h['pass_number']} "
                    f"({h['token_count_est']} tokens) ---"
                )
            parts.append(f"[REFINEMENT_HISTORY]\n"
                         + "\n".join(history_lines)
                         + "\n[/REFINEMENT_HISTORY]")

        # 5. Current plan
        parts.append(f"[CURRENT_PLAN]\n{session.current_plan}\n[/CURRENT_PLAN]")

        # 6. Final instruction
        parts.append(
            f"This is refinement pass {pass_number} of {session.max_passes}. "
            f"Output ONLY the refined extraction plan. "
            f"Preserve the # <EXTRACT_TO: path> ... # </EXTRACT_TO> tag format. "
            f"Do not add commentary outside the plan."
        )

        return "\n\n".join(parts)

    def _system_prompt(self, pass_number, max_passes):
        """Return a system prompt tailored to the current refinement phase."""
        base = (
            "You are a code architecture expert specializing in monolith decomposition. "
            "You are reviewing an extraction plan for a Python application called 'The DISMANTLER'.\n"
            "The application follows a strict architecture:\n"
            "- Backend modules live in src/backend/ and src/backend/modules/\n"
            "- UI modules live in src/ui/modules/\n"
            "- Controllers handle action dispatch (schema-based)\n"
            "- Backend modules must NEVER import tkinter or any UI library\n"
            "- UI modules must be stateless (no database logic)\n"
            "- All UI-backend communication goes through BackendEngine.execute_task()\n\n"
            "The extraction plan uses # <EXTRACT_TO: target_path> ... # </EXTRACT_TO> tags "
            "to mark code blocks and their destination files.\n\n"
        )

        if pass_number == 1:
            phase = (
                "PHASE: STRUCTURAL REVIEW (Pass 1)\n"
                "Focus on:\n"
                "- Are the EXTRACT_TO targets correct? (Controllers to backend/, UI to ui/modules/)\n"
                "- Are there missing extraction blocks that should be separated?\n"
                "- Are there blocks that should NOT be extracted (too small, too coupled)?\n"
                "- Does each block have a clear single responsibility?\n"
                "Refine the plan to fix any structural issues."
            )
        elif pass_number == 2 and max_passes > 2:
            phase = (
                "PHASE: DEPENDENCY ANALYSIS (Pass 2)\n"
                "Focus on:\n"
                "- Will the extracted blocks have circular imports?\n"
                "- What imports need to be added to each extracted file?\n"
                "- Are there shared utilities that should be extracted to a common module?\n"
                "- Are there hidden dependencies (global state, module-level variables)?\n"
                "Add import annotations and dependency notes to the plan."
            )
        elif pass_number == max_passes:
            phase = (
                f"PHASE: FINAL VALIDATION (Pass {pass_number})\n"
                "Focus on:\n"
                "- Verify every EXTRACT_TO block targets a valid, correct path\n"
                "- Ensure no block violates the backend/UI separation rule\n"
                "- Check that the extraction order won't break intermediate states\n"
                "- Add any missing docstrings or type hints to extracted blocks\n"
                "Output the final, production-ready extraction plan."
            )
        else:
            phase = (
                f"PHASE: ITERATIVE REFINEMENT (Pass {pass_number})\n"
                "Review the current plan and improve it:\n"
                "- Fix any remaining architectural issues\n"
                "- Optimize the extraction groupings\n"
                "- Ensure naming conventions match the existing codebase\n"
                "- Look for edge cases or error handling gaps\n"
                "Make targeted, meaningful improvements."
            )

        return base + phase

    # ── helpers ─────────────────────────────────────────────

    def _read_file(self, file_path):
        """Read file content from disk. Pure filesystem, no UI."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except (OSError, UnicodeDecodeError) as e:
            self.log(f"Failed to read {file_path}: {e}")
            return ""
