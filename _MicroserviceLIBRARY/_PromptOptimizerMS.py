import json
import logging
from typing import List, Dict, Any, Callable, Optional
from microservice_std_lib import service_metadata, service_endpoint
REFINE_SYSTEM_PROMPT = 'You are a world-class prompt engineer. Given an original prompt and specific feedback, provide an improved, refined version of the prompt that incorporates the feedback. Return ONLY the refined prompt text, no preamble.'
VARIATION_SYSTEM_PROMPT = 'You are a creative AI assistant. Generate {num} innovative and diverse variations of the following prompt. Return the result as a valid JSON array of strings. Example: ["variation 1", "variation 2"]'
logger = logging.getLogger('PromptOpt')

@service_metadata(name='PromptOptimizer', version='1.0.0', description='Uses an LLM to refine prompts or generate variations.', tags=['llm', 'prompt-engineering', 'optimization'], capabilities=['network:outbound'], internal_dependencies=['microservice_std_lib'], external_dependencies=[])
class PromptOptimizerMS:
    """
    The Tuner: Uses an LLM to refine prompts or generate variations.
    Requires an 'inference_func' to be passed in the config, which accepts a string
    and returns a string (simulating an LLM call).
    """

    def __init__(self, config: Optional[Dict[str, Any]]=None):
        self.config = config or {}
        self.infer: Callable[[str], str] = self.config.get('inference_func', lambda x: 'Error: No inference function configured.')

    @service_endpoint(inputs={'draft_prompt': 'str', 'feedback': 'str'}, outputs={'refined_prompt': 'str'}, description='Rewrites a prompt based on feedback.', tags=['llm', 'refine'], side_effects=['network:outbound'])
    def refine_prompt(self, draft_prompt: str, feedback: str) -> str:
        """
        Rewrites a prompt based on feedback.
        """
        full_prompt = f'{REFINE_SYSTEM_PROMPT}\n\n[Original Prompt]:\n{draft_prompt}\n\n[Feedback]:\n{feedback}\n\n[Refined Prompt]:'
        logger.info('Refining prompt...')
        try:
            result = self.infer(full_prompt)
            return result.strip()
        except Exception as e:
            logger.error(f'Refinement failed: {e}')
            return draft_prompt

    @service_endpoint(inputs={'draft_prompt': 'str', 'num_variations': 'int', 'context_data': 'Dict'}, outputs={'variations': 'List[str]'}, description='Generates multiple versions of a prompt for testing.', tags=['llm', 'variations'], side_effects=['network:outbound'])
    def generate_variations(self, draft_prompt: str, num_variations: int=3, context_data: Optional[Dict[str, Any]]=None) -> List[str]:
        """
        Generates multiple versions of a prompt for testing.
        """
        meta_prompt = VARIATION_SYSTEM_PROMPT.format(num=num_variations)
        prompt_content = draft_prompt
        if context_data:
            prompt_content += f'\n\n--- Context ---\n{json.dumps(context_data, indent=2)}'
        full_prompt = f'{meta_prompt}\n\n[Original Prompt]:\n{prompt_content}\n\n[JSON Array of Variations]:'
        logger.info(f'Generating {num_variations} variations...')
        try:
            raw_response = self.infer(full_prompt)
            start = raw_response.find('[')
            end = raw_response.rfind(']') + 1
            if start == -1 or end == 0:
                logger.warning('No JSON array found in response. Returning raw response.')
                return [raw_response]
            clean_json = raw_response[start:end]
            variations = json.loads(clean_json)
            if isinstance(variations, list):
                return [str(v) for v in variations]
            return []
        except Exception as e:
            logger.error(f'Variation generation failed: {e}')
            return []
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    def mock_llm(prompt: str) -> str:
        if '[Refined Prompt]' in prompt:
            return 'You are a helpful assistant who speaks like a pirate. How may I help ye?'
        if '[JSON Array]' in prompt:
            return '["Variation A: Pirate Mode", "Variation B: Formal Mode", "Variation C: Concise Mode"]'
        return 'Error'
    optimizer = PromptOptimizerMS({'inference_func': mock_llm})
    print('Service ready:', optimizer)
    print('--- Test: Refine ---')
    draft = 'Help me.'
    feedback = 'Make it sound like a pirate.'
    refined = optimizer.refine_prompt(draft, feedback)
    print(f'Original: {draft}')
    print(f'Refined:  {refined}')
    print('\n--- Test: Variations ---')
    vars = optimizer.generate_variations(draft, num_variations=3)
    for i, v in enumerate(vars):
        print(f' {i + 1}. {v}')
