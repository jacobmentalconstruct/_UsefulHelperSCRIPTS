"""
LIBRARY: Microservice Standard Lib
VERSION: 2.0.0
ROLE: Provides decorators for tagging Python classes as AI-discoverable services.
"""

import functools
import inspect
from typing import Dict, List, Any, Optional, Type

# ==============================================================================
# DECORATORS (The "Writer" Tools)
# ==============================================================================

def service_metadata(name: str, version: str, description: str, tags: List[str], capabilities: List[str] = None, dependencies: List[str] = None, side_effects: List[str] = None):
    """
    Class Decorator.
    Labels a Microservice class with high-level metadata for the Catalog.
    """
    def decorator(cls):
        cls._is_microservice = True
        cls._service_info = {
            "name": name,
            "version": version,
            "description": description,
            "tags": tags,
            "capabilities": capabilities or [],
            "dependencies": dependencies or [],
            "side_effects": side_effects or []
        }
        return cls
    return decorator

def service_endpoint(inputs: Dict[str, str], outputs: Dict[str, str], description: str, tags: List[str] = None, side_effects: List[str] = None, mode: str = "sync"):
    """
    Method Decorator.
    Defines the 'Socket' that the AI Architect can plug into.
    
    :param inputs: Dict of {arg_name: type_string} (e.g. {"query": "str"})
    :param outputs: Dict of {return_name: type_string} (e.g. {"results": "List[Dict]"})
    :param description: What this specific function does.
    :param tags: Keywords for searching (e.g. ["search", "read-only"])
    :param side_effects: List of impact types (e.g. ["network:outbound", "disk:write"])
    :param mode: 'sync', 'async', or 'ui_event'
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        
        # Attach metadata to the function object itself
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
    for name, method in inspect.getmembers(service_cls, predicate=inspect.isfunction):
        # Unwrap decorators if necessary to find our tags
        # (Though usually the wrapper has the tag attached)
        endpoint_info = getattr(method, "_endpoint_info", None)
        
        if endpoint_info:
            schema["endpoints"].append(endpoint_info)

    return schema
