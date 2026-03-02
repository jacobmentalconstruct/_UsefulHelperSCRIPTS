from microservice_std_lib import service_metadata, service_endpoint
from typing import Dict, Any, Optional

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
        # Initialize your core logic/engines here

    @service_endpoint(
        inputs={"param1": "str", "param2": "int"},
        outputs={"result": "str"},
        description="Detailed description of what this specific method does.",
        tags=["action"],
        side_effects=["filesystem:write"] # Be explicit for the AI safety
    )
    def perform_action(self, param1: str, param2: int = 10) -> Dict[str, Any]:
        # Your translated logic goes here
        return {"result": f"Processed {param1}"}

if __name__ == "__main__":
    # Standard independent test block for the catalogue
    svc = YourServiceMS()
    print("Service ready:", svc)
    # Add a print test of your logic here