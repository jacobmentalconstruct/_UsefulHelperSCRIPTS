"""
microservice_std_lib_registry.py
Extension to microservice_std_lib — adds the ServiceRegistry and the
register() hook that all microservices expose.

Designed to latch onto what @service_metadata already provides:
  name, version, tags, capabilities, side_effects, internal_dependencies, external_dependencies

Nothing in existing services needs to change except the injection of register().
"""

from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class ServiceRegistry:
    """
    Central registry. Managers instantiate one of these and pass it to
    each service's register() call at startup.
    """

    def __init__(self):
        self._services: Dict[str, Dict[str, Any]] = {}

    def register(
        self,
        name: str,
        version: str,
        tags: List[str],
        capabilities: List[str],
        instance: Any,
        group: Optional[str] = None,
    ) -> None:
        self._services[name] = {
            "name": name,
            "version": version,
            "tags": tags,
            "capabilities": capabilities,
            "group": group,
            "instance": instance,
        }

    def get(self, name: str) -> Optional[Any]:
        entry = self._services.get(name)
        return entry["instance"] if entry else None

    def list_all(self) -> List[Dict[str, Any]]:
        return [
            {k: v for k, v in entry.items() if k != "instance"}
            for entry in self._services.values()
        ]

    def list_by_tag(self, tag: str) -> List[str]:
        return [
            name for name, entry in self._services.items()
            if tag in entry.get("tags", [])
        ]

    def list_by_capability(self, capability: str) -> List[str]:
        return [
            name for name, entry in self._services.items()
            if capability in entry.get("capabilities", [])
        ]

    def health_all(self) -> Dict[str, Any]:
        results = {}
        for name, entry in self._services.items():
            inst = entry["instance"]
            try:
                results[name] = inst.get_health()
            except Exception as e:
                results[name] = {"status": "error", "error": str(e)}
        return results


# ---------------------------------------------------------------------------
# The register() method body to inject into existing microservices
# ---------------------------------------------------------------------------
#
# Every microservice gets exactly this method injected.
# It reads _service_info or _meta which @service_metadata attaches to the class.
#
# INJECTION TEMPLATE — the inject script copies this verbatim into each class:
#
#     def register(self, registry, group: str = None):
#         registry.register(
#             name=meta.get('name', self.__class__.__name__),
#             version=meta.get('version', '0.0.0'),
#             tags=meta.get('tags', []),
#             capabilities=meta.get('capabilities', []),
#             instance=self,
#             group=group,
#         )
#
# ---------------------------------------------------------------------------

REGISTER_METHOD_SOURCE = '''
    def register(self, registry, group=None):
        """Auto-injected registration hook. Latches onto @service_metadata fields."""
        meta = getattr(self, '_service_info', None) or getattr(self, '_meta', {})
        registry.register(
            name=meta.get('name', self.__class__.__name__),
            version=meta.get('version', '0.0.0'),
            tags=meta.get('tags', []),
            capabilities=meta.get('capabilities', []),
            instance=self,
            group=group,
        )
'''
