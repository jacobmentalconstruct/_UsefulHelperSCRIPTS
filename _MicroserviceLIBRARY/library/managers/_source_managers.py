"""
managers.py
Six manager classes — one per group.
Each manager owns a ServiceRegistry, instantiates its services, and registers them.
Managers are what the orchestrator layer talks to.
"""

import time
from typing import Any, Dict, List, Optional

from microservice_std_lib_registry import ServiceRegistry

from storage_group import (
    Blake3HashMS, MerkleRootMS, VerbatimStoreMS, TemporalChainMS
)
from structure_group import (
    DagOpsMS, IntervalIndexMS, DirectedFlowMS
)
from meaning_relation_observability_manifold_groups import (
    SemanticSearchMS, LexicalIndexMS, OntologyMS,
    PropertyGraphMS, IdentityAnchorMS,
    LayerHealthMS, WalkerTraceMS,
    CrossLayerResolverMS, ManifoldProjectorMS, HypergraphMS,
)


class BaseManager:
    """Shared base — all managers expose registry, health, and service lookup."""

    GROUP_NAME = 'base'

    def __init__(self):
        self.start_time = time.time()
        self.registry = ServiceRegistry()
        self._boot()

    def _boot(self):
        raise NotImplementedError

    def get(self, name: str) -> Optional[Any]:
        return self.registry.get(name)

    def health(self) -> Dict[str, Any]:
        return self.registry.health_all()

    def list_services(self) -> List[Dict[str, Any]]:
        return self.registry.list_all()


# ---------------------------------------------------------------------------
# StorageManager
# ---------------------------------------------------------------------------

class StorageManager(BaseManager):
    GROUP_NAME = 'storage'

    def _boot(self):
        services = [Blake3HashMS(), MerkleRootMS(), VerbatimStoreMS(), TemporalChainMS()]
        for svc in services:
            svc.register(self.registry, group=self.GROUP_NAME)

    @property
    def hasher(self) -> Blake3HashMS:
        return self.get('Blake3HashMS')

    @property
    def merkle(self) -> MerkleRootMS:
        return self.get('MerkleRootMS')

    @property
    def verbatim(self) -> VerbatimStoreMS:
        return self.get('VerbatimStoreMS')

    @property
    def temporal(self) -> TemporalChainMS:
        return self.get('TemporalChainMS')


# ---------------------------------------------------------------------------
# StructureManager
# ---------------------------------------------------------------------------

class StructureManager(BaseManager):
    GROUP_NAME = 'structure'

    def _boot(self):
        services = [DagOpsMS(), IntervalIndexMS(), DirectedFlowMS()]
        for svc in services:
            svc.register(self.registry, group=self.GROUP_NAME)

    @property
    def dag(self) -> DagOpsMS:
        return self.get('DagOpsMS')

    @property
    def intervals(self) -> IntervalIndexMS:
        return self.get('IntervalIndexMS')

    @property
    def flow(self) -> DirectedFlowMS:
        return self.get('DirectedFlowMS')


# ---------------------------------------------------------------------------
# MeaningManager
# ---------------------------------------------------------------------------

class MeaningManager(BaseManager):
    GROUP_NAME = 'meaning'

    def _boot(self):
        services = [SemanticSearchMS(), LexicalIndexMS(), OntologyMS()]
        for svc in services:
            svc.register(self.registry, group=self.GROUP_NAME)

    @property
    def semantic(self) -> SemanticSearchMS:
        return self.get('SemanticSearchMS')

    @property
    def lexical(self) -> LexicalIndexMS:
        return self.get('LexicalIndexMS')

    @property
    def ontology(self) -> OntologyMS:
        return self.get('OntologyMS')


# ---------------------------------------------------------------------------
# RelationManager
# ---------------------------------------------------------------------------

class RelationManager(BaseManager):
    GROUP_NAME = 'relation'

    def _boot(self):
        services = [PropertyGraphMS(), IdentityAnchorMS()]
        for svc in services:
            svc.register(self.registry, group=self.GROUP_NAME)

    @property
    def property_graph(self) -> PropertyGraphMS:
        return self.get('PropertyGraphMS')

    @property
    def identity(self) -> IdentityAnchorMS:
        return self.get('IdentityAnchorMS')


# ---------------------------------------------------------------------------
# ObservabilityManager
# ---------------------------------------------------------------------------

class ObservabilityManager(BaseManager):
    GROUP_NAME = 'observability'

    def _boot(self):
        services = [LayerHealthMS(), WalkerTraceMS()]
        for svc in services:
            svc.register(self.registry, group=self.GROUP_NAME)

    @property
    def health_monitor(self) -> LayerHealthMS:
        return self.get('LayerHealthMS')

    @property
    def walker_trace(self) -> WalkerTraceMS:
        return self.get('WalkerTraceMS')

    def poll_all_managers(self, managers: List[BaseManager]) -> Dict[str, Any]:
        """Ask health monitor to poll every manager's registry."""
        combined = {}
        for mgr in managers:
            combined[mgr.GROUP_NAME] = mgr.health()
        return combined


# ---------------------------------------------------------------------------
# ManifoldManager
# ---------------------------------------------------------------------------

class ManifoldManager(BaseManager):
    GROUP_NAME = 'manifold'

    def _boot(self):
        services = [CrossLayerResolverMS(), ManifoldProjectorMS(), HypergraphMS()]
        for svc in services:
            svc.register(self.registry, group=self.GROUP_NAME)

    @property
    def resolver(self) -> CrossLayerResolverMS:
        return self.get('CrossLayerResolverMS')

    @property
    def projector(self) -> ManifoldProjectorMS:
        return self.get('ManifoldProjectorMS')

    @property
    def hypergraph(self) -> HypergraphMS:
        return self.get('HypergraphMS')
