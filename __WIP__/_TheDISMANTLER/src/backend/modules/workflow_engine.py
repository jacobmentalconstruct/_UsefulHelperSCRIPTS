"""
WorkflowEngine – JSON-driven sequential tool orchestrator.
Executes a named sequence of steps, threading output from step N
as input to step N+1, with status callbacks for UI updates.
Zero UI dependencies.
"""
from datetime import datetime


class WorkflowEngine:
    """
    Runs a named workflow defined as a JSON schema of sequential steps.
    Each step maps to a (system, action) pair dispatched through
    BackendEngine.execute_task().

    Usage:
        engine = WorkflowEngine(execute_fn=backend.execute_task, log=backend.log)
        result = engine.run(
            workflow={"name": "Default Curation", "steps": ["curate", "code_metrics"]},
            initial_context={"file": "/path/to.py"},
            status_callback=my_callback,
        )
    """

    # Maps step names to (system, action, default_extras)
    _STEP_REGISTRY = {
        "curate":        ("curate", "curate_file", {}),
        "code_metrics":  ("code_metrics", "analyze", {}),
        "get_entities":  ("curate", "get_entities", {}),
        "get_hierarchy": ("curate", "get_hierarchy", {}),
        "ai_refinement": ("ai", "generate", {
            "system_prompt": "You are a code analysis and refinement assistant."
        }),
        "patch_preview": ("export", "preview", {}),
    }

    def __init__(self, execute_fn, log=None):
        """
        Args:
            execute_fn: BackendEngine.execute_task callable
            log: logging callback
        """
        self.execute = execute_fn
        self.log = log or (lambda msg: None)

    @classmethod
    def register_step(cls, name, system, action, defaults=None):
        """Register a new step type at runtime."""
        cls._STEP_REGISTRY[name] = (system, action, defaults or {})

    @classmethod
    def list_steps(cls):
        """Return available step names."""
        return list(cls._STEP_REGISTRY.keys())

    # ── execution ──────────────────────────────────────────

    def run(self, workflow, initial_context, status_callback=None):
        """
        Execute a workflow synchronously (call from a background thread).

        Args:
            workflow: {"name": "...", "steps": ["curate", "code_metrics", ...]}
            initial_context: starting context dict (e.g. {"file": "/path/to.py"})
            status_callback: fn({"step": N, "total": M, "step_name": str, "status": str})

        Returns:
            {"status": "ok"/"error", "context": final_context, "results": [...]}
        """
        steps = workflow.get("steps", [])
        name = workflow.get("name", "Unnamed Workflow")
        total = len(steps)
        context = dict(initial_context)
        results = []
        had_failure = False

        self.log(f"Workflow '{name}' starting ({total} steps)")
        start = datetime.now()

        for i, step_name in enumerate(steps):
            step_num = i + 1

            if status_callback:
                status_callback({
                    "step": step_num,
                    "total": total,
                    "step_name": step_name,
                    "status": f"Running {step_name}...",
                })

            # Fail fast on unknown steps
            if step_name not in self._STEP_REGISTRY:
                error_msg = (
                    f"Unknown step: '{step_name}' "
                    f"(available: {', '.join(self._STEP_REGISTRY)})"
                )
                self.log(f"  Step {step_num}: {error_msg}")
                results.append({
                    "step": step_name, "status": "error", "message": error_msg
                })
                if status_callback:
                    status_callback({
                        "step": step_num, "total": total,
                        "step_name": step_name,
                        "status": f"FAILED: {error_msg}",
                    })
                elapsed = (datetime.now() - start).total_seconds()
                return {
                    "status": "error",
                    "message": error_msg,
                    "context": context,
                    "results": results,
                    "elapsed": elapsed,
                }

            system, action, defaults = self._STEP_REGISTRY[step_name]
            schema = {"system": system, "action": action}
            schema.update(defaults)
            schema.update(self._map_context_to_schema(step_name, context))

            self.log(f"  Step {step_num}/{total}: {step_name} -> {system}.{action}")

            try:
                result = self.execute(schema)
                step_status = result.get("status", "error")
                results.append({
                    "step": step_name,
                    "status": step_status,
                    "data": result,
                })

                if step_status == "ok":
                    # Merge into context with collision warnings
                    for k, v in result.items():
                        if k in ("status", "message"):
                            continue
                        if k in context and k not in initial_context:
                            self.log(
                                f"    Warning: key '{k}' overwritten "
                                f"by step '{step_name}'"
                            )
                        context[k] = v
                    # Also store namespaced copy for debugging
                    context[f"_step_{step_name}"] = result
                else:
                    had_failure = True
                    self.log(f"  Step {step_num} failed: {result.get('message')}")

            except Exception as e:
                had_failure = True
                self.log(f"  Step {step_num} exception: {e}")
                results.append({
                    "step": step_name, "status": "error", "message": str(e),
                })

        elapsed = (datetime.now() - start).total_seconds()
        overall_status = "error" if had_failure else "ok"

        status_msg = f"Workflow '{name}' finished ({elapsed:.1f}s)."
        if had_failure:
            status_msg += " Some steps had errors."

        if status_callback:
            status_callback({
                "step": total,
                "total": total,
                "step_name": "complete",
                "status": status_msg,
            })

        self.log(f"Workflow '{name}' {overall_status} in {elapsed:.1f}s")
        return {
            "status": overall_status,
            "context": context,
            "results": results,
            "elapsed": elapsed,
        }

    # ── context mapping ────────────────────────────────────

    def _map_context_to_schema(self, step_name, context):
        """
        Map accumulated context keys to the schema keys expected by each step.
        Handles naming mismatches between step outputs and inputs.
        """
        mapped = {}

        # Universal: file path
        if "file" in context:
            mapped["file"] = context["file"]
            mapped["path"] = context["file"]

        # Universal: pass buffer content if available
        if "content" in context:
            mapped["content"] = context["content"]

        # For patch_preview: build the files list
        if step_name == "patch_preview" and "content" in context:
            original = context.get("content", "")
            patched = context.get(
                "patched_content",
                context.get("ai_response", original),
            )
            mapped["files"] = [{
                "path": context.get("file", ""),
                "content": patched,
            }]

        # For ai_refinement: build the prompt
        if step_name == "ai_refinement":
            summary_parts = []
            if "entities" in context:
                summary_parts.append(
                    f"Entities found: {len(context['entities'])}"
                )
            if "metrics" in context:
                m = context["metrics"]
                summary_parts.append(
                    f"Complexity: {m.get('cyclomatic_complexity', '?')} "
                    f"({m.get('complexity_rating', '?')})"
                )
            summary = ". ".join(summary_parts)
            code = context.get("content", "")[:4000]
            mapped["prompt"] = (
                f"Analyze and suggest improvements for this code.\n"
                f"{summary}\n\nCode:\n{code}"
            )
            mapped["model"] = context.get("model", "")

        return mapped
