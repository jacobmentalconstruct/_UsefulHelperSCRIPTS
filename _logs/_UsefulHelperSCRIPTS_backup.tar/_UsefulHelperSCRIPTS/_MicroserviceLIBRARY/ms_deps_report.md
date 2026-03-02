# Microservice Dependency Report

- Root: `C:\Users\petya\Documents\Jacob's BIN\_UsefulHelperSCRIPTS\_MicroserviceLIBRARY`
- Files scanned: **58**
- Parsed OK: **58**
- Rewritten files: **31**

## Per-file summary

| File | Parsed | Changed | Internal deps | External deps | Notes/Errors |
|---|---:|---:|---|---|---|
| `_ArchiveBotMS.py` | ✅ | ✅ | base_service, microservice_std_lib |  | Synced manifest header deps (Option A). |
| `_AuthMS.py` | ✅ | ✅ | microservice_std_lib |  | Synced manifest header deps (Option A). |
| `_CartridgeServiceMS.py` | ✅ | ✅ | base_service, microservice_std_lib | sqlite_vec | Synced manifest header deps (Option A). |
| `_ChalkBoardMS.py` | ✅ | ✅ | base_service, microservice_std_lib | webview | Synced manifest header deps (Option A). |
| `_ChunkingRouterMS.py` | ✅ | ✅ | _PythonChunkerMS, base_service, microservice_std_lib |  | Synced manifest header deps (Option A). |
| `_CodeChunkerMS.py` | ✅ | ✅ | base_service, microservice_std_lib |  | Synced manifest header deps (Option A). |
| `_CodeFormatterMS.py` | ✅ | ✅ | microservice_std_lib |  | Synced manifest header deps (Option A). |
| `_CodeGrapherMS.py` | ✅ | ✅ | base_service, microservice_std_lib |  | Synced manifest header deps (Option A). |
| `_CodeJanitorMS.py` | ✅ | ✅ | microservice_std_lib |  | Synced manifest header deps (Option A). |
| `_CognitiveMemoryMS.py` | ✅ | ✅ | base_service, microservice_std_lib | pydantic | Synced manifest header deps (Option A). |
| `_ContentExtractorMS.py` | ✅ | ✅ | microservice_std_lib | beautifulsoup4, bs4, pypdf | Synced manifest header deps (Option A). |
| `_ContextAggregatorMS.py` | ✅ | ✅ | microservice_std_lib |  | Synced manifest header deps (Option A). |
| `_ContextPackerMS.py` | ✅ | ✅ | microservice_std_lib |  | Synced manifest header deps (Option A). |
| `_DiffEngineMS.py` | ✅ | ✅ | microservice_std_lib |  | Synced manifest header deps (Option A). |
| `_EnvironmentManagerMS.py` | ✅ | ✅ | microservice_std_lib |  | Synced manifest header deps (Option A). |
| `_ExplorerWidgetMS.py` | ✅ | ✅ | base_service, microservice_std_lib | ttk | Synced manifest header deps (Option A). |
| `_FingerprintScannerMS.py` | ✅ | ✅ | microservice_std_lib |  | Synced manifest header deps (Option A). |
| `_GitPilotMS.py` | ✅ | ✅ | microservice_std_lib | git | Synced manifest header deps (Option A). |
| `_HeuristicSumMS.py` | ✅ | ✅ | base_service, microservice_std_lib |  | Synced manifest header deps (Option A). |
| `_IngestEngineMS.py` | ✅ | ✅ | base_service, microservice_std_lib | requests | Synced manifest header deps (Option A). |
| `_IntakeServiceMS.py` | ✅ | ✅ | _CartridgeServiceMS, _ScannerMS, base_service, document_utils, microservice_std_lib | bs4, requests | Synced manifest header deps (Option A). |
| `_IsoProcessMS.py` | ✅ |  | microservice_std_lib |  |  |
| `_LexicalSearchMS.py` | ✅ |  | microservice_std_lib |  |  |
| `_LibrarianMS.py` | ✅ | ✅ | microservice_std_lib | requests | Synced manifest header deps (Option A). |
| `_LibrarianServiceMS.py` | ✅ | ✅ | microservice_std_lib | requests | Synced manifest header deps (Option A). |
| `_LogViewMS.py` | ✅ |  | microservice_std_lib |  |  |
| `_MonacoHostMS.py` | ✅ |  | microservice_std_lib | webview |  |
| `_NetworkLayoutMS.py` | ✅ |  | microservice_std_lib | networkx |  |
| `_NeuralGraphEngineMS.py` | ✅ | ✅ | base_service, microservice_std_lib | pygame | Synced manifest header deps (Option A). |
| `_NeuralGraphViewerMS.py` | ✅ | ✅ | _NeuralGraphEngineMS, base_service, microservice_std_lib | PIL | Synced manifest header deps (Option A). |
| `_NeuralServiceMS.py` | ✅ |  | microservice_std_lib | requests |  |
| `_ProjectForgeMS.py` | ✅ | ✅ | microservice_std_lib |  | Synced manifest header deps (Option A). |
| `_PromptOptimizerMS.py` | ✅ |  | microservice_std_lib |  |  |
| `_PromptVaultMS.py` | ✅ |  | microservice_std_lib | jinja2, pydantic |  |
| `_PythonChunkerMS.py` | ✅ |  | microservice_std_lib |  |  |
| `_RefineryServiceMS.py` | ✅ |  | _CartridgeServiceMS, _ChunkingRouterMS, _NeuralServiceMS, microservice_std_lib |  |  |
| `_RegexWeaverMS.py` | ✅ |  | microservice_std_lib |  |  |
| `_RoleManagerMS.py` | ✅ |  | microservice_std_lib | pydantic |  |
| `_SandboxManagerMS.py` | ✅ |  | microservice_std_lib |  |  |
| `_ScannerMS.py` | ✅ | ✅ | base_service, microservice_std_lib |  | Synced manifest header deps (Option A). |
| `_ScoutMS.py` | ✅ |  | microservice_std_lib | bs4, requests |  |
| `_SearchEngineMS.py` | ✅ |  | microservice_std_lib | requests, sqlite_vec |  |
| `_SemanticChunkerMS.py` | ✅ |  | microservice_std_lib |  |  |
| `_ServiceRegistryMS.py` | ✅ |  | microservice_std_lib |  |  |
| `_SpinnerThingyMaBobberMS.py` | ✅ |  | microservice_std_lib |  |  |
| `_SysInspectorMS.py` | ✅ |  | microservice_std_lib |  |  |
| `_TasklistVaultMS.py` | ✅ |  | microservice_std_lib |  |  |
| `_TelemetryServiceMS.py` | ✅ |  | microservice_std_lib |  |  |
| `_TextChunkerMS.py` | ✅ |  | microservice_std_lib |  |  |
| `_ThoughtStreamMS.py` | ✅ |  | microservice_std_lib |  |  |
| `_TkinterAppShellMS.py` | ✅ | ✅ | _TkinterThemeManagerMS, microservice_std_lib |  | Synced manifest header deps (Option A). |
| `_TkinterSmartExplorerMS.py` | ✅ | ✅ | microservice_std_lib |  | Synced manifest header deps (Option A). |
| `_TkinterThemeManagerMS.py` | ✅ | ✅ | microservice_std_lib |  | Synced manifest header deps (Option A). |
| `_TkinterUniButtonMS.py` | ✅ |  | microservice_std_lib |  |  |
| `_TreeMapperMS.py` | ✅ |  | microservice_std_lib |  |  |
| `_VectorFactoryMS.py` | ✅ |  | microservice_std_lib | chromadb, faiss, numpy |  |
| `_WebScraperMS.py` | ✅ |  | microservice_std_lib | httpx, readability |  |
| `_WorkbenchLayoutMS.py` | ✅ | ✅ | microservice_std_lib |  | Synced manifest header deps (Option A). |

## Aggregate external dependencies (requirements candidates)

- PIL
- beautifulsoup4
- bs4
- chromadb
- faiss
- git
- httpx
- jinja2
- networkx
- numpy
- pydantic
- pygame
- pypdf
- readability
- requests
- sqlite_vec
- ttk
- webview
