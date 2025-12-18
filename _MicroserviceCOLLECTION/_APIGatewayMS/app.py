"""
SERVICE: APIGateway
ROLE: Expose a local Python object as an HTTP API surface.
INPUTS:
- backend_core: Arbitrary Python object providing callable methods.
OUTPUTS:
- Running FastAPI+Uvicorn gateway.
NOTES:
This service dynamically binds Python callables to REST endpoints and handles
inbound API routing, health checks, and CORS configuration.
"""

import logging
import sys
import threading
import asyncio
from typing import Any, Dict, List, Optional, Callable

from microservice_std_lib import service_metadata, service_endpoint

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("APIGateway")

# ==============================================================================
# CONFIGURATION
# ==============================================================================
API_TITLE = "Microservice Gateway"
API_VERSION = "2.0.0"
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8099
# ==============================================================================

@service_metadata(
    name="APIGateway",
    version="2.0.0",
    description="Exposes local Python objects as REST APIs via FastAPI.",
    tags=["networking", "api", "gateway"],
    capabilities=["network:inbound"],
)
class APIGatewayMS:
    """
    ROLE: Expose arbitrary Python objects as REST API endpoints.
    INPUTS:
    - config: Optional dict containing backend_core and runtime settings.
    OUTPUTS:
    - FastAPI application instance with dynamically attached endpoints.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.core = self.config.get("backend_core")
        self.server_thread: Optional[threading.Thread] = None
        self.server_instance = None # Handle for the uvicorn server object
        self._available = False

        # Lazy import to avoid hard crash if libs are missing
        try:
            from fastapi import FastAPI
            from fastapi.middleware.cors import CORSMiddleware
            from pydantic import BaseModel
            import uvicorn

            self.FastAPI = FastAPI
            self.CORSMiddleware = CORSMiddleware
            self.BaseModel = BaseModel
            self.uvicorn = uvicorn
            self._available = True
        except ImportError as e:
            logger.critical(f"Missing dependency: {e}")
            logger.error("Run: pip install -r requirements.txt")
            return

        # Create FastAPI app
        self.app = self.FastAPI(title=API_TITLE, version=API_VERSION)

        # Enable CORS
        self.app.add_middleware(
            self.CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Setup base routes
        self._setup_system_routes()

    # ------------------------------------------------------------------ #
    # System routes
    # ------------------------------------------------------------------ #
    def _setup_system_routes(self) -> None:
        @self.app.get("/")
        def root():
            return {"status": "online", "service": API_TITLE, "version": API_VERSION}

        @self.app.get("/health")
        def health():
            backend_type = type(self.core).__name__ if self.core is not None else "None"
            return {"status": "healthy", "backend_type": backend_type}

    # ------------------------------------------------------------------ #
    # Dynamic endpoints
    # ------------------------------------------------------------------ #
    @service_endpoint(
        inputs={"path": "str", "method": "str", "handler": "Callable"},
        outputs={},
        description="Dynamically adds a route to the API.",
        tags=["configuration", "routing"],
        side_effects=["runtime:state_change"],
    )
    def add_endpoint(self, path: str, method: str, handler: Callable) -> None:
        """
        Dynamically adds a route to the API.

        :param path: URL path (e.g., "/search")
        :param method: "GET" or "POST"
        :param handler: The function to run
        """
        if not self._available:
            logger.error("APIGatewayMS is not available; cannot add endpoint.")
            return

        method_upper = method.upper()
        # Note: We apply the handler directly. FastAPI introspects the handler
        # signature for Pydantic models.
        if method_upper == "POST":
            self.app.post(path)(handler)
        elif method_upper == "GET":
            self.app.get(path)(handler)
        elif method_upper == "PUT":
            self.app.put(path)(handler)
        elif method_upper == "DELETE":
            self.app.delete(path)(handler)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        logger.debug(f"Attached endpoint [{method_upper}] {path}")

    # ------------------------------------------------------------------ #
    # Server control
    # ------------------------------------------------------------------ #
    @service_endpoint(
        inputs={"host": "str", "port": "int", "blocking": "bool"},
        outputs={},
        description="Starts the Uvicorn server.",
        tags=["execution", "server"],
        mode="sync",
        side_effects=["network:inbound", "process:blocking"],
    )
    def start(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        blocking: bool = True,
    ) -> None:
        """
        Starts the Uvicorn server.
        """
        if not self._available:
            logger.error("APIGatewayMS not available; FastAPI/uvicorn not installed.")
            return

        # Configure Uvicorn programmatically
        config = self.uvicorn.Config(
            app=self.app, 
            host=host, 
            port=port, 
            log_level="info"
        )
        self.server_instance = self.uvicorn.Server(config)

        if blocking:
            logger.info(f"Starting API Gateway (Blocking) at http://{host}:{port}")
            self.server_instance.run()
        else:
            logger.info(f"Starting API Gateway (Threaded) at http://{host}:{port}")
            self.server_thread = threading.Thread(target=self.server_instance.run, daemon=True)
            self.server_thread.start()

    def stop(self):
        """Stops the server if running in threaded mode."""
        if self.server_instance:
            self.server_instance.should_exit = True
            if self.server_thread:
                self.server_thread.join(timeout=5)
            logger.info("Server stopped.")


# --- Independent Test Block ---
if __name__ == "__main__":
    # 1. Define a Mock Backend (The "Core" Logic)
    class MockBackend:
        def search(self, query: str):
            return [f"Result for {query} 1", f"Result for {query} 2"]

        def echo(self, msg: str):
            return f"Echo: {msg}"

    backend = MockBackend()

    # 2. Init Gateway
    gateway = APIGatewayMS({"backend_core": backend})

    if gateway._available:
        # 3. Define Request Models (Pydantic) for strong typing in Swagger
        class SearchReq(gateway.BaseModel):
            query: str
            limit: int = 10

        class EchoReq(gateway.BaseModel):
            message: str

        # 4. Map Backend Methods to API Endpoints
        def search_endpoint(req: SearchReq):
            """Searches the mock backend."""
            return {"results": backend.search(req.query), "limit": req.limit}

        def echo_endpoint(req: EchoReq):
            """Echoes a message."""
            return {"response": backend.echo(req.message)}

        gateway.add_endpoint("/v1/search", "POST", search_endpoint)
        gateway.add_endpoint("/v1/echo", "POST", echo_endpoint)

        # 5. Run
        try:
            gateway.start(port=8099, blocking=True)
        except KeyboardInterrupt:
            gateway.stop()