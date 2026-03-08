"""Constants used by the app-factory implementation."""

from __future__ import annotations

from pathlib import Path

APP_FACTORY_VERSION = "0.1.0"

LIBRARY_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = LIBRARY_ROOT.parent
CATALOG_DIR = LIBRARY_ROOT / "catalog"
DEFAULT_CATALOG_DB_PATH = CATALOG_DIR / "catalog.db"
DEFAULT_MAPPING_REPORT_PATH = CATALOG_DIR / "canonical_mapping_report.json"

CATALOG_BUILD_TABLE = "catalog_builds"

VALID_VENDOR_MODES = {"module_ref", "static"}
VALID_RESOLUTION_PROFILES = {"app_ready", "strict", "explicit_pack"}
SPECIAL_UI_PACKS = {"explicit"}
IGNORED_EXTERNAL_DEPENDENCIES = {"ttk", "tkinter", "tk"}

FOUNDRY_THEME = {
    "background": "#14181D",
    "foreground": "#F3EEE7",
    "accent": "#C9773B",
    "accent_alt": "#2D7F86",
    "panel_bg": "#10161E",
    "terminal_bg": "#0A0F16",
    "muted": "#8C97A6",
    "border": "#334155",
}

GROUPED_MANAGER_SERVICE_MAP = {
    "storage": [
        "Blake3HashMS",
        "MerkleRootMS",
        "VerbatimStoreMS",
        "TemporalChainMS",
    ],
    "structure": [
        "DagOpsMS",
        "IntervalIndexMS",
        "DirectedFlowMS",
    ],
    "meaning": [
        "SemanticSearchMS",
        "LexicalIndexMS",
        "OntologyMS",
    ],
    "relation": [
        "PropertyGraphMS",
        "IdentityAnchorMS",
    ],
    "observability": [
        "LayerHealthMS",
        "WalkerTraceMS",
    ],
    "manifold": [
        "CrossLayerResolverMS",
        "ManifoldProjectorMS",
        "HypergraphMS",
    ],
}

GROUPED_SERVICE_TO_LAYER = {
    service_name: layer
    for layer, service_names in GROUPED_MANAGER_SERVICE_MAP.items()
    for service_name in service_names
}

UI_PACKS = {
    "tkinter_base_pack": {
        "pack_id": "tkinter_base_pack",
        "name": "Tkinter Base Pack",
        "kind": "ui_pack",
        "version": "1.0.0",
        "services": [
            {
                "class_name": "TkinterAppShellMS",
                "service_name": "TkinterAppShell",
                "module_import": "library.microservices.ui._TkinterAppShellMS",
            },
            {
                "class_name": "TkinterThemeManagerMS",
                "service_name": "TkinterThemeManager",
                "module_import": "library.microservices.ui._TkinterThemeManagerMS",
            },
            {
                "class_name": "WorkbenchLayoutMS",
                "service_name": "WorkbenchLayout",
                "module_import": "library.microservices.ui._WorkbenchLayoutMS",
            },
        ],
        "manifest": {
            "layout": {
                "type": "row",
                "weight": 1,
                "children": [
                    {"type": "panel", "id": "services", "weight": 1},
                    {
                        "type": "col",
                        "weight": 3,
                        "children": [
                            {"type": "panel", "id": "details", "weight": 3},
                            {"type": "panel", "id": "actions", "weight": 1},
                        ],
                    },
                ],
            },
            "theme": dict(FOUNDRY_THEME),
        },
    },
    "headless_pack": {
        "pack_id": "headless_pack",
        "name": "Headless Pack",
        "kind": "ui_pack",
        "version": "1.0.0",
        "services": [],
        "manifest": {
            "layout": {"type": "panel", "id": "headless", "weight": 1},
            "theme": dict(FOUNDRY_THEME),
        },
    },
}

APP_BLUEPRINT_TEMPLATES = {
    "headless_scanner": {
        "template_id": "headless_scanner",
        "name": "Headless Scanner",
        "description": "Minimal headless starter app around FingerprintScannerMS.",
        "microservices": ["FingerprintScannerMS"],
        "vendor_mode": "module_ref",
        "resolution_profile": "app_ready",
        "settings_defaults": {"app_title": "Headless Scanner", "assistant_enabled": False},
        "tags": ["headless", "core", "starter"],
    },
    "ui_explorer_workbench": {
        "template_id": "ui_explorer_workbench",
        "name": "Explorer Workbench",
        "description": "Tkinter starter app centered on ExplorerWidgetMS.",
        "microservices": ["ExplorerWidgetMS"],
        "vendor_mode": "module_ref",
        "resolution_profile": "app_ready",
        "settings_defaults": {"app_title": "Explorer Workbench", "assistant_enabled": False},
        "tags": ["ui", "tkinter", "starter"],
    },
    "semantic_pipeline_tool": {
        "template_id": "semantic_pipeline_tool",
        "name": "Semantic Pipeline Tool",
        "description": "Headless pipeline starter app for ingest and semantic chunking flows.",
        "microservices": ["IngestEngineMS", "SemanticChunkerMS"],
        "vendor_mode": "module_ref",
        "resolution_profile": "app_ready",
        "settings_defaults": {"app_title": "Semantic Pipeline Tool", "assistant_enabled": False},
        "tags": ["pipeline", "headless", "starter"],
    },
    "storage_layer_lab": {
        "template_id": "storage_layer_lab",
        "name": "Storage Layer Lab",
        "description": "Grouped-layer storage lab for hashing, Merkle roots, verbatim storage, and temporal chaining.",
        "microservices": ["Blake3HashMS", "MerkleRootMS", "VerbatimStoreMS", "TemporalChainMS"],
        "vendor_mode": "module_ref",
        "resolution_profile": "app_ready",
        "settings_defaults": {"app_title": "Storage Layer Lab", "assistant_enabled": False},
        "tags": ["storage", "grouped", "starter"],
    },
    "manifold_layer_lab": {
        "template_id": "manifold_layer_lab",
        "name": "Manifold Layer Lab",
        "description": "Grouped-layer manifold lab for cross-layer resolution and projection experiments.",
        "microservices": ["CrossLayerResolverMS", "ManifoldProjectorMS", "HypergraphMS"],
        "vendor_mode": "module_ref",
        "resolution_profile": "app_ready",
        "settings_defaults": {"app_title": "Manifold Layer Lab", "assistant_enabled": False},
        "tags": ["manifold", "grouped", "starter"],
    },
}

PACK_SERVICE_CLASS_NAMES = {
    service["class_name"]
    for pack in UI_PACKS.values()
    for service in pack["services"]
}

DEFAULT_RUNTIME_COMPAT_DIRS = [
    LIBRARY_ROOT,
    LIBRARY_ROOT / "managers",
    LIBRARY_ROOT / "orchestrators",
    LIBRARY_ROOT / "microservices" / "core",
    LIBRARY_ROOT / "microservices" / "db",
    LIBRARY_ROOT / "microservices" / "grouped",
    LIBRARY_ROOT / "microservices" / "meaning",
    LIBRARY_ROOT / "microservices" / "observability",
    LIBRARY_ROOT / "microservices" / "pipeline",
    LIBRARY_ROOT / "microservices" / "reference",
    LIBRARY_ROOT / "microservices" / "relation",
    LIBRARY_ROOT / "microservices" / "storage",
    LIBRARY_ROOT / "microservices" / "structure",
    LIBRARY_ROOT / "microservices" / "ui",
]

LOCAL_HELPER_MODULES = {
    "microservice_std_lib",
    "base_service",
    "document_utils",
}
