import logging
from typing import Dict, Any

class BaseService:
    """
    Standard parent class for all microservices. 
    Provides consistent logging and identity management.
    """
    def __init__(self, name: str):
        self._service_info = {
            "name": name, 
            "id": name.lower().replace(" ", "_")
        }
        
        # NOTE: Do not call logging.basicConfig() per service instance.
        # Configure logging once at the application entrypoint (app.py / UI shell),
        # then services simply acquire named loggers.
        self.logger = logging.getLogger(name)

    def log_info(self, message: str):
        self.logger.info(message)

    def log_error(self, message: str):
        self.logger.error(message)

    def log_warning(self, message: str):
        self.logger.warning(message)

