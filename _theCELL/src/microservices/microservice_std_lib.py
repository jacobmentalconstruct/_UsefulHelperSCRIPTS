"""
LIBRARY: Microservice Standard Lib
VERSION: 2.1.0
ROLE: Provides decorators for tagging Python classes as AI-discoverable services.

Change (2.1.0):
- Split dependencies into:
    internal_dependencies: local modules / microservices to vendor with the app
    external_dependencies: pip-installable packages (requirements.txt)
- Keep legacy "dependencies" as an alias for external_dependencies for backward compatibility.
- Accept unknown keyword args in @service_metadata(...) to prevent older/newer services from crashing
  (e.g. when a runner passes additional fields).
"""

import functools
import inspect
from typing import Dict, List, Any, Optional, Type

# ==============================================================================
# DECORATORS (The "Writer" Tools)
# ==============================================================================

def service_metadata(
    name: str,
    version: str,
    description: str,
    tags: List[str],
    capabilities: Optional[List[str]] = None,

    # Legacy field (kept for backward compatibility):
    # Historically this mixed stdlib + pip deps. Going forward, treat this as *external* deps.
    dependencies: Optional[List[str]] = None,

    # New fields (preferred):
    internal_dependencies: Optional[List[str]] = None,
    external_dependencies: Optional[List[str]] = None,

    # Side effects / operational hints
    side_effects: Optional[List[str]] = None,

    # Forward-compat: ignore unknown keyword args instead of crashing older/newer services
    **_ignored_kwargs: Any,
):
    """
    Class Decorator.
    Labels a Microservice class with high-level metadata for the Catalog.

    Dependency semantics:
      - internal_dependencies: local modules and/or other microservice modules that must be shipped with an app
      - external_dependencies: third-party pip packages (requirements.txt)
      - dependencies (legacy): treated as external_dependencies when external_dependencies is not provided
    """
    # Prefer explicit new key, otherwise fall back to legacy dependencies
    ext = external_dependencies if external_dependencies is not None else (dependencies or [])
    intl = internal_dependencies or []

    def decorator(cls):
        cls._is_microservice = True
        cls._service_info = {
            "name": name,
            "version": version,
            "description": description,
            "tags": tags,
            "capabilities": capabilities or [],

            # New keys
            "internal_dependencies": intl,
            "external_dependencies": ext,

            # Legacy alias (keep existing tooling working)
            "dependencies": ext,

            "side_effects": side_effects or []
        }
        return cls
    return decorator


def service_endpoint(
    inputs: Dict[str, str],
    outputs: Dict[str, str],
    description: str,
    tags: Optional[List[str]] = None,
    side_effects: Optional[List[str]] = None,
    mode: str = "sync",
):
    """
    Method Decorator.
    Defines the 'Socket' that the AI Architect can plug into.

    :param inputs: Dict of {arg_name: type_string} (e.g. {"query": "str"})
    :param outputs: Dict of {return_name: type_string}
    :param description: What the endpoint does
    :param tags: List of categories (e.g. ["read", "write"])
    :param side_effects: List of side effects (e.g. ["filesystem:write", "db:write"])
    :param mode: "sync" or "async" (informational unless your runtime uses it)
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        # Attach metadata to the function object itself
        wrapper._is_endpoint = True
        wrapper._endpoint_info = {
            "name": func.__name__,
            "inputs": inputs,
            "outputs": outputs,
            "description": description,
            "tags": tags or [],
            "side_effects": side_effects or [],
            "mode": mode
        }
        return wrapper
    return decorator


# ==============================================================================
# INTROSPECTION (The "Reader" Tools)
# ==============================================================================

def extract_service_schema(service_cls: Type) -> Dict[str, Any]:
    """
    Scans a decorated Service Class and returns a JSON-serializable schema
    of its metadata and all its exposed endpoints.

    This is what the AI Agent uses to 'read' the manual.
    """
    if not getattr(service_cls, "_is_microservice", False):
        raise ValueError(f"Class {service_cls.__name__} is not decorated with @service_metadata")

    schema = {
        "meta": getattr(service_cls, "_service_info", {}),
        "endpoints": []
    }

    # Inspect all methods of the class
    for _, method in inspect.getmembers(service_cls, predicate=inspect.isfunction):
        endpoint_info = getattr(method, "_endpoint_info", None)
        if endpoint_info:
            schema["endpoints"].append(endpoint_info)

    return schema
