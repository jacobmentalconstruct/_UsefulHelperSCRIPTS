"""
SERVICE_NAME: _PromptOptimizerMS
ENTRY_POINT: __PromptOptimizerMS.py
DEPENDENCIES: None
"""

import json
import logging
from typing import List, Dict, Any, Callable, Optional
from microservice_std_lib import service_metadata, service_endpoint

# ==============================================================================
# CONFIGURATION: META-PROMPTS
# ==============================================================================
# The system prompt used to turn the LLM into a Prompt Engineer
REFINE_SYSTEM_PROMPT = (
    "You are a world-class prompt engineer. "
    "Given an original prompt and specific feedback, "
    "provide an improved, refined version of the prompt that incorporates the feedback. "
    "Return ONLY the refined prompt text, no preamble."
)

# The system prompt used to generate A/B test variations
VARIATION_SYSTEM_PROMPT = (
    "You are a creative AI assistant. "
    "Generate {num} innovative and diverse variations of the following prompt. "
    "Return the result as a valid JSON array of strings. "
    "Example: [\"variation 1\", \"variation 2\"]"
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger("PromptOpt")
# ==============================================================================

@service_metadata(
name="PromptOptimizer",
version="1.0.0",
description="Uses an LLM to refine prompts or generate variations.",
tags=["llm", "prompt-engineering", "optimization"],
capabilities=["network:outbound"]
)
class PromptOptimizerMS:
    """
The Tuner: Uses an LLM to refine prompts or generate variations.
"""
def __init__(self, config: Optional[Dict[str, Any]] = None):
self.config = config or {}
self.infer = self.config.get("inference_func")

    @service_endpoint(
    inputs={"draft_prompt": "str", "feedback": "str"},
    outputs={"refined_prompt": "str"},
    description="Rewrites a prompt based on feedback.",
    tags=["llm", "refine"],
    side_effects=["network:outbound"]
    )
def refine_prompt(self, draft_prompt: str, feedback: str) -> str:
    """
    Rewrites a prompt based on feedback.
    """
        full_prompt = (
            f"{REFINE_SYSTEM_PROMPT}\n\n"
            f"[Original Prompt]:\n{draft_prompt}\n\n"
            f"[Feedback]:\n{feedback}\n\n"
            f"[Refined Prompt]:"
        )
        
        log.info("Refining prompt...")
        try:
            result = self.infer(full_prompt)
            return result.strip()
        except Exception as e:
            log.error(f"Refinement failed: {e}")
            return draft_prompt # Fallback to original

@service_endpoint(
    inputs={"draft_prompt": "str", "num_variations": "int", "context_data": "Dict"},
    outputs={"variations": "List[str]"},
    description="Generates multiple versions of a prompt for testing.",
    tags=["llm", "variations"],
    side_effects=["network:outbound"]
)
def generate_variations(self, draft_prompt: str, num_variations: int = 3, context_data: Optional[Dict] = None) -> List[str]:
    """
    Generates multiple versions of a prompt for testing.
    """
        meta_prompt = VARIATION_SYSTEM_PROMPT.format(num=num_variations)
        
        prompt_content = draft_prompt
        if context_data:
            prompt_content += f"\n\n--- Context ---\n{json.dumps(context_data, indent=2)}"

        full_prompt = (
            f"{meta_prompt}\n\n"
            f"[Original Prompt]:\n{prompt_content}\n\n"
            f"[JSON Array of Variations]:"
        )

        log.info(f"Generating {num_variations} variations...")
        try:
            # We explicitly ask for JSON, but LLMs are chatty, so we might need cleaning logic here
            raw_response = self.infer(full_prompt)
            
            # Simple cleanup to find the JSON array if the LLM added text around it
            start = raw_response.find('[')
            end = raw_response.rfind(']') + 1
            if start == -1 or end == 0:
                raise ValueError("No JSON array found in response")
                
            clean_json = raw_response[start:end]
            variations = json.loads(clean_json)
            
            if isinstance(variations, list):
                return [str(v) for v in variations]
            return []
            
        except Exception as e:
            log.error(f"Variation generation failed: {e}")
            return []

# --- Independent Test Block ---
if __name__ == "__main__":
    # 1. Mock Inference Engine (Simulating an LLM)
    def mock_llm(prompt: str) -> str:
        if "[Refined Prompt]" in prompt:
            return "You are a helpful assistant who speaks like a pirate. How may I help ye?"
        if "[JSON Array]" in prompt:
            return '["Variation A: Pirate Mode", "Variation B: Formal Mode", "Variation C: Concise Mode"]'
        return "Error"

    optimizer = PromptOptimizerMS({"inference_func": mock_llm})
    print("Service ready:", optimizer)

    # 2. Test Refine
    print("--- Test: Refine ---")
    draft = "Help me."
feedback = "Make it sound like a pirate."
    refined = optimizer.refine_prompt(draft, feedback)
    print(f"Original: {draft}")
    print(f"Refined:  {refined}")

    # 3. Test Variations
    print("\n--- Test: Variations ---")
    vars = optimizer.generate_variations(draft, num_variations=3)
    for i, v in enumerate(vars):
        print(f" {i+1}. {v}")
