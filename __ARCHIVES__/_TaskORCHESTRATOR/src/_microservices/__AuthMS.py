"""
SERVICE_NAME: _AuthMS
ENTRY_POINT: __AuthMS.py
DEPENDENCIES: None
"""

import base64
import hashlib
import json
import logging
import time
from typing import Any, Dict, Optional

from microservice_std_lib import service_metadata, service_endpoint, BaseService

# ==============================================================================
# CONFIGURATION
# ==============================================================================
DEFAULT_SECRET_KEY = "super_secret_cortex_key"
DEFAULT_SALT = "cortex_salt"

logger = logging.getLogger("Auth")

# ==============================================================================
# SERVICE DEFINITION
# ==============================================================================
@service_metadata(
    name="Auth",
    version="1.0.0",
    description="Manages user authentication and signed session tokens.",
    tags=["auth", "security", "crypto"],
    capabilities=["crypto"],
    dependencies=["hashlib", "json", "time", "base64"],
    side_effects=[]
)
class AuthMS(BaseService):
    """
    ROLE: Simple authentication microservice providing username/password login
          and signed session tokens.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__("Auth")
        self.config = config or {}
        self.secret_key: str = self.config.get("secret_key", DEFAULT_SECRET_KEY)

        # In a real scenario, this might load from a secure config file or DB.
        # For now, we keep a minimal in-memory user database[cite: 21].
        self.users_db: Dict[str, str] = {
            "admin": self._hash_password("admin123"),
        }

    # ==========================================================================
    # CORE ENDPOINTS
    # ==========================================================================

    @service_endpoint(
        inputs={"username": "str", "password": "str"},
        outputs={"token": "Optional[str]"},
        description="Attempts to log in and returns a signed session token.",
        tags=["auth", "security", "session"],
    )
    def login(self, username: str, password: str) -> Optional[str]:
        """
        Attempt to log in with the provided username and password.
        """
        if username not in self.users_db:
            return None

        stored_hash = self.users_db[username]
        if self._verify_password(password, stored_hash):
            return self._create_token(username)

        return None

    @service_endpoint(
        inputs={"token": "str"},
        outputs={"is_valid": "bool"},
        description="Checks whether a token is valid and not expired.",
        tags=["auth", "security"],
    )
    def validate_session(self, token: str) -> bool:
        """
        Check if a serialized token is valid and not expired[cite: 26].
        """
        payload = self._decode_token(token)
        return payload is not None

    # ==========================================================================
    # INTERNAL HELPERS
    # ==========================================================================

    def _hash_password(self, password: str) -> str:
        """
        Securely hashes a password using SHA-256 with a static salt[cite: 29].
        """
        return hashlib.sha256((password + DEFAULT_SALT).encode("utf-8")).hexdigest()

    def _verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """
        Verifies a provided password against the stored hash[cite: 30].
        """
        return self._hash_password(plain_password) == hashed_password

    def _create_token(self, user_id: str, expires_in: int = 3600) -> str:
        """
        Generates a signed session token containing sub, exp, iat, and scope[cite: 31].
        """
        now = int(time.time())
        payload = {
            "sub": user_id,
            "exp": now + expires_in,
            "iat": now,
            "scope": "admin",
        }

        json_payload = json.dumps(payload).encode("utf-8")
        token_part = base64.b64encode(json_payload).decode("utf-8")

        signature = hashlib.sha256((token_part + self.secret_key).encode("utf-8")).hexdigest()
        return f"{token_part}.{signature}"

    def _decode_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Parses and validates the incoming token.
        Returns the payload if valid, None otherwise.
        """
        try:
            if not token or "." not in token:
                return None

            token_part, signature = token.split(".", 1)

            # Recalculate signature to verify integrity
            recalc_signature = hashlib.sha256(
                (token_part + self.secret_key).encode("utf-8")
            ).hexdigest()

            if signature != recalc_signature:
                return None  # Invalid signature

            # Decode payload
            payload_json = base64.b64decode(token_part).decode("utf-8")
            payload: Dict[str, Any] = json.loads(payload_json)

            # Check expiration
            if payload.get("exp", 0) < time.time():
                return None  # Expired

            return payload

        except Exception:
            # Intentionally swallow details here and just treat token as invalid[cite: 37].
            logger.exception("Failed to decode or validate auth token.")
            return None


# ==============================================================================
# SELF-TEST / RUNNER
# ==============================================================================
if __name__ == "__main__":
    svc = AuthMS()
    print(f"Service Ready: {svc}")
    
    # Simple test
    token = svc.login("admin", "admin123")
    print(f"Token Generated: {token is not None}")
    if token:
        is_valid = svc.validate_session(token)
        print(f"Token Valid: {is_valid}")
