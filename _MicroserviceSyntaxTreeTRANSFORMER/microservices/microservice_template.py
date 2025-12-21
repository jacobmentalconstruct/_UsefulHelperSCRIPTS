"""
Standardized Microservice Template
"""
from microservice_std_lib import service_metadata, service_endpoint
from base_service import BaseService

@service_metadata(
    name="{{SERVICE_NAME}}",
    version="1.0.0",
    description="{{DESCRIPTION}}",
    tags=[],
    capabilities=[]
)
class {{CLASS_NAME}}(BaseService):
    def __init__(self):
        super().__init__("{{SERVICE_NAME}}")
        # {{INIT_LOGIC}}

    # {{ENDPOINTS}}
