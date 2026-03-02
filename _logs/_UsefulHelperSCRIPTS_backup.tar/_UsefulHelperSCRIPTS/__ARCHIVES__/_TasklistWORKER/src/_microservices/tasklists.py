def get_tasklist_names(mode: str):
    tl = _TASKLISTS.get(mode, {})
    return list(tl.keys())

def load_tasklist_by_name(mode: str, name: str) -> dict:
    return _TASKLISTS[mode][name]

_TASKLISTS = {
    "validate_patch": {
        "validate_patch_v0": {
            "name": "validate_patch_v0",
            "mode": "validate_patch",
            "steps": [
                {
                    "id": "V1",
                    "name": "Normalize patch JSON",
                    "enabled": True,
                    "model": "qwen2.5:7b-coder",
                    "ollama_options": {"temperature": 0.0},
                    "system_prompt": "You are a strict JSON normalizer. Output ONLY valid JSON. No commentary.",
                    "user_prompt_template": "PATCH_JSON_INPUT:\n{{state.inputs.existing_patch_json}}\n\nReturn valid JSON only.",
                    "expects": "json",
                    "output_key": "working.candidate_patch",
                    "validators": ["json_parse"],
                    "on_fail": "retry"
                },
                {
                    "id": "V2",
                    "name": "Enforce schema and output final patch JSON",
                    "enabled": True,
                    "model": "qwen2.5:7b-coder",
                    "ollama_options": {"temperature": 0.0},
                    "system_prompt": "Output ONLY JSON that matches EXACT schema: {hunks:[{description,search_block,replace_block,use_patch_indent}]}. No extra keys. hunks non-empty. use_patch_indent boolean.",
                    "user_prompt_template": "CANDIDATE:\n{{state.working.candidate_patch}}\n\nReturn schema-valid patch JSON only.",
                    "expects": "patch_json",
                    "output_key": "outputs.final_patch",
                    "validators": ["schema_strict"],
                    "on_fail": "retry"
                }
            ]
        }
    },
    "repair_patch": {
        "repair_patch_v0": {
            "name": "repair_patch_v0",
            "mode": "repair_patch",
            "steps": [
                {
                    "id": "R1",
                    "name": "Rewrite hunks to match current file",
                    "enabled": True,
                    "model": "qwen2.5:7b-coder",
                    "ollama_options": {"temperature": 0.2},
                    "system_prompt": (
                        "You are a patch surgeon for TokenizingPATCHER.\n"
                        "MUST output ONLY schema-valid patch JSON.\n"
                        "Rules:\n"
                        "- Every search_block MUST appear verbatim in TARGET_FILE.\n"
                        "- replace_block must be concrete (no placeholders).\n"
                        "- No extra keys."
                    ),
                    "user_prompt_template": (
                        "TARGET_FILE:\n{{state.inputs.target_file_text}}\n\n"
                        "FAILING_PATCH_JSON:\n{{state.inputs.existing_patch_json}}\n\n"
                        "ERROR_LOG:\n{{state.inputs.error_log_text}}\n\n"
                        "Produce corrected patch JSON."
                    ),
                    "expects": "patch_json",
                    "output_key": "outputs.final_patch",
                    "validators": ["schema_strict", "match_search_blocks"],
                    "on_fail": "retry"
                }
            ]
        }
    },
    "create_patch": {
        "create_patch_v0": {
            "name": "create_patch_v0",
            "mode": "create_patch",
            "steps": [
                {
                    "id": "C1",
                    "name": "Generate patch from snippet + file",
                    "enabled": True,
                    "model": "qwen2.5:7b-coder",
                    "ollama_options": {"temperature": 0.2},
                    "system_prompt": (
                        "Generate TokenizingPATCHER patch JSON.\n"
                        "Hard rules:\n"
                        "- Output ONLY schema-valid patch JSON.\n"
                        "- Every search_block MUST be verbatim substring from TARGET_FILE.\n"
                        "- replace_block must be concrete and placeholder-free.\n"
                        "- No extra keys."
                    ),
                    "user_prompt_template": (
                        "TARGET_FILE:\n{{state.inputs.target_file_text}}\n\n"
                        "CHANGE_SNIPPET:\n{{state.inputs.snippet_text}}\n\n"
                        "Create patch JSON."
                    ),
                    "expects": "patch_json",
                    "output_key": "outputs.final_patch",
                    "validators": ["schema_strict", "match_search_blocks"],
                    "on_fail": "retry"
                }
            ]
        }
    }
}
