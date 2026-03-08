"""Central orchestrator hub for grouped layer managers."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..managers.managers import (
    ManifoldManager,
    MeaningManager,
    ObservabilityManager,
    RelationManager,
    StorageManager,
    StructureManager,
)


class LayerHub:
    """Single access point for all layer managers in the grouped library."""

    def __init__(self):
        self.storage = StorageManager()
        self.structure = StructureManager()
        self.meaning = MeaningManager()
        self.relation = RelationManager()
        self.observability = ObservabilityManager()
        self.manifold = ManifoldManager()

        self._managers: Dict[str, Any] = {
            "storage": self.storage,
            "structure": self.structure,
            "meaning": self.meaning,
            "relation": self.relation,
            "observability": self.observability,
            "manifold": self.manifold,
        }

    def get_manager(self, layer: str) -> Optional[Any]:
        return self._managers.get(str(layer).strip().lower())

    def list_layers(self) -> List[str]:
        return sorted(self._managers.keys())

    def health(self) -> Dict[str, Any]:
        return {layer: manager.health() for layer, manager in self._managers.items()}

    def list_services(self) -> Dict[str, List[Dict[str, Any]]]:
        return {layer: manager.list_services() for layer, manager in self._managers.items()}

    def resolve_service(self, service_name: str) -> Optional[Any]:
        target = str(service_name).strip()
        for manager in self._managers.values():
            svc = manager.get(target)
            if svc is not None:
                return svc
        return None


__all__ = ["LayerHub"]