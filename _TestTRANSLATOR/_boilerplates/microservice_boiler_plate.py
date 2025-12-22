from microservice_std_lib import service_metadata, service_endpoint
from typing import Dict, Any, Optional

# NOTE: The [Mad Libs] Script will inject Imports and Helper Functions above this line automatically.

@service_metadata(
    name="YourServiceName",
    version="1.0.0",
    description="Briefly describe the 'Purpose' here.",
    tags=["category", "utility"],
    capabilities=["filesystem:read"] # Optional: what it actually touches
)
class YourServiceMS:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.timeout = self.config.get("timeout_seconds", 60)
        
        # Setup standard logger
        self.log = logging.getLogger(self.__class__.__name__)
        if not self.log.handlers:
            logging.basicConfig(level=logging.INFO)

    @service_endpoint(
        inputs={"param1": "str", "param2": "int"},
        outputs={"result": "str"},
        description="Detailed description of what this specific method does.",
        tags=["action"],
        side_effects=["filesystem:write"] 
    )
    def execute(self, payload: Any, config: Optional[Dict[str, Any]] = None) -> Any:
        # [INJECT LOGIC HERE]
        return {}

if __name__ == "__main__":
    # Standard independent test block for the catalogue
    svc = YourServiceMS()
    print("Service ready:", svc)
    # Add a print test of your logic here