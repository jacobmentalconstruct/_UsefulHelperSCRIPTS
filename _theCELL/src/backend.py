from src.microservices._IngestEngineMS import IngestEngineMS

class Backend:
    def __init__(self):
        # Use the existing IngestEngine to talk to Ollama [cite: 46]
        from src.microservices._IngestEngineMS import IngestEngineMS
        from src.microservices._FeedbackValidationMS import FeedbackValidationMS
        
        self.engine = IngestEngineMS()
        self.validator = FeedbackValidationMS()
        self.system_role = "You are a helpful AI assistant."

    def get_models(self):
        """Fetches available Ollama models."""
        models = self.engine.get_available_models()
        return models if models else ["No Models Found"]

    def set_system_role(self, role_text):
        self.system_role = role_text

    def process_submission(self, content, model, role, prompt):
        """
        Refined submission logic.
        Integrates with IngestEngine and prepares for LLM call.
        """
        self.system_role = role
        clean_content = content.strip()
        
        # Prepare for CognitiveMemory integration
        print(f"[STATUS] Logic Hub Processing Submission...")
        print(f"[MODEL] {model}")
        print(f"[ROLE] {self.system_role}")
        print(f"[PROMPT] {prompt}")
        print(f"[PAYLOAD] {len(clean_content)} chars")


