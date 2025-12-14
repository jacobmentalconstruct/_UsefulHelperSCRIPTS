import logging
import sys

class BaseService:
    """
    Standard base class for all _NeoCORTEX microservices.
    Provides unified logging and error handling.
    """
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.log = logging.getLogger(service_name)
        
        # Configure logging if not already set up
        if not self.log.handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter('%(asctime)s [%(name)s] %(levelname)s: %(message)s', datefmt='%H:%M:%S')
            handler.setFormatter(formatter)
            self.log.addHandler(handler)
            self.log.setLevel(logging.INFO)

    def log_info(self, msg: str):
        self.log.info(msg)

    def log_error(self, msg: str):
        self.log.error(msg)
