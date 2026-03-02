import json
from typing import Any, Dict, List, Optional, Tuple

from src._microservices.ollama_client import OllamaClient
from src._microservices.template_engine import resolve_template

_client = OllamaClient()


def _set_by_path(state: dict, path: str, value):
    # path like "working.step_outputs.S1" or "chat.last_response"
    parts = path.split(".")
    cur = state
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value


def _get_by_path(state: dict, path: str):
    parts = path.split(".")
    cur = state
    for p in parts:
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur


def _ensure_state_defaults(state: dict) -> dict:
    """
    Runner-friendly defaults so UI can pass a minimal state in.
    """
    state.setdefault("chat", {})
    state["chat"].setdefault("history", [])          # list[{role, content}]
    state["chat"].setdefault("last_user", "")
    state["chat"].setdefault("last_response", "")

    state.setdefault("working", {})
    state["working"].setdefault("step_outputs", {})  # dict step_id -> output
    state["working"].setdefault("thoughts", [])      # list[{step_id, name, summary, errors?}]
    state["working"].setdefault("notes", [])         # list[{step_id, name, errors}]

    state.setdefault("outputs", {})
    state["outputs"].setdefault("final", "")

    return state


def _chain_prompt(base_prompt: str, chain_mode: str, last: str) -> str:
    """
    chain_mode:
      - "none": base_prompt only
      - "last": base_prompt + "\n\n---\nLAST_OUTPUT:\n" + last
      - "replace": replace occurrences of "{{last}}" in base_prompt
    """
    last = last or ""
    chain_mode = (chain_mode or "none").strip().lower()

    if chain_mode == "none":
        return base_prompt
    if chain_mode == "last":
        if not last:
            return base_prompt
        return f"{base_prompt}\n\n---\nLAST_OUTPUT:\n{last}"
    if chain_mode == "replace":
        return base_prompt.replace("{{last}}", last)

    # unknown -> safe default
    return base_prompt


def _safe_json_loads(text: str) -> Tuple[Optional[Any], Optional[str]]:
    try:
        return json.loads(text), None
    except Exception as e:
        return None, str(e)


def _run_helper_summary(
    helper_model: str,
    helper_system: str,
    helper_template: str,
    step_name: str,
    step_output: str,
    state: dict,
    options: Optional[dict] = None
) -> str:
    """
    Summarize what happened in this step. The template can reference:
      - {{state....}} via template_engine
      - {{step_name}}
      - {{step_output}}
    """
    tmp_state = dict(state)
    tmp_state.setdefault("_step_ctx", {})
    tmp_state["_step_ctx"]["step_name"] = step_name
    tmp_state["_step_ctx"]["step_output"] = step_output

    # allow easy placeholders without complicating template_engine:
    prompt = helper_template.replace("{{step_name}}", step_name).replace("{{step_output}}", step_output)
    prompt = resolve_template(prompt, tmp_state)

    raw = _client.generate(
        model=helper_model,
        system=helper_system,
        prompt=prompt,
        options=options or {"temperature": 0.2}
    )
    return (raw or "").strip()


def run_tasklist(
    state: dict,
    tasklist: dict,
    chat_model_default: str,
    helper_model_default: str,
) -> dict:
    """
    Generic tasklist runner.

    Each step:
      - builds a prompt from user_prompt_template (+ optional chaining)
      - calls an Ollama model
      - stores output to output_key
      - optionally runs helper summary (thought bubble)

    Expected step fields (minimal):
      - id (str)
      - name (str)
      - enabled (bool)
      - model (optional; defaults to chat_model_default)
      - system_prompt (str)
      - user_prompt_template (str)
      - chain_mode ("none" | "last" | "replace") optional
      - output_key (defaults to "working.step_outputs.<id>")
      - expects ("text" | "json") optional
      - thought_enabled (bool) optional
      - thought_model (optional; defaults helper_model_default)
      - thought_system_prompt (optional)
      - thought_prompt_template (optional)
    """
    state = _ensure_state_defaults(state)

    steps = tasklist.get("steps", [])
    last = state["chat"].get("last_response", "")

    for step in steps:
        if not step.get("enabled", True):
            continue

        step_id = step.get("id", "STEP?")
        step_name = step.get("name", step_id)

        model = step.get("model") or chat_model_default
        system = step.get("system_prompt", "")
        template = step.get("user_prompt_template", "")
        options = step.get("ollama_options") or {}

        chain_mode = step.get("chain_mode", "none")
        expects = step.get("expects", "text").strip().lower()

        output_key = step.get("output_key") or f"working.step_outputs.{step_id}"

        # 1) build prompt
        base_prompt = resolve_template(template, state)
        prompt = _chain_prompt(base_prompt, chain_mode, last)

        # 2) call model
        raw = _client.generate(model=model, system=system, prompt=prompt, options=options)
        raw_stripped = (raw or "").strip()

        # 3) parse/store
        produced_obj = None
        if expects == "json":
            produced_obj, err = _safe_json_loads(raw_stripped)
            if err:
                state["working"]["notes"].append({
                    "step_id": step_id,
                    "name": step_name,
                    "errors": [f"json_parse failed: {err}"]
                })
                # fall back to raw text storage
                _set_by_path(state, output_key, raw_stripped)
                last = raw_stripped
            else:
                _set_by_path(state, output_key, produced_obj)
                last = json.dumps(produced_obj, ensure_ascii=False)
        else:
            _set_by_path(state, output_key, raw_stripped)
            last = raw_stripped

        # record runner-level last_response
        state["chat"]["last_response"] = last

        # 4) thought bubble (helper model)
        if step.get("thought_enabled", True):
            helper_model = step.get("thought_model") or helper_model_default
            helper_system = step.get("thought_system_prompt") or (
                "Summarize what happened in this step in 1-3 bullet points. "
                "Be concrete. No fluff. No preamble."
            )
            helper_template = step.get("thought_prompt_template") or (
                "STEP: {{step_name}}\n\nOUTPUT:\n{{step_output}}\n\n"
                "Return 1-3 bullets: what changed / what was decided / what to do next."
            )

            try:
                summary = _run_helper_summary(
                    helper_model=helper_model,
                    helper_system=helper_system,
                    helper_template=helper_template,
                    step_name=step_name,
                    step_output=last,
                    state=state,
                    options={"temperature": 0.2}
                )
            except Exception as e:
                summary = f"- Thought summary failed: {e}"

            state["working"]["thoughts"].append({
                "step_id": step_id,
                "name": step_name,
                "summary": summary
            })

    state["outputs"]["final"] = state["chat"].get("last_response", "")
    return state
