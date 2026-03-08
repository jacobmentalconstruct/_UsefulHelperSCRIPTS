# Layered Library Layout

This folder is a centralized, grouped view of the microservice ecosystem.

## Top-Level
- `library/microservices/`: grouped microservice files by functional layer.
- `library/managers/`: manager classes that own registries and service startup.
- `library/orchestrators/`: orchestrator entry points (`LayerHub`) over all managers.
- `library/modules/`: non-microservice module specs/helpers (e.g., WASM specs).
- `library/tools/`: operational helpers (e.g., register-hook injector).
- `library/catalog/`: generated grouping artifacts and plans.

## Microservice Layers
- `reference`: extracted/pilfered reference services.
- `ui`: tkinter/view/theme/explorer-facing services.
- `storage`: hash/verbatim/temporal persistence services.
- `structure`: DAG/interval/flow/structural services.
- `meaning`: semantic/lexical/ontology services.
- `relation`: graph/identity relation services.
- `observability`: health/trace/monitoring services.
- `manifold`: cross-layer resolver/projector/hypergraph services.
- `pipeline`: ingest/chunk/embed/manifest services.
- `db`: sqlite/query/search/schema services.
- `core`: uncategorized/general core services.

## Entry Point
Use `library.orchestrators.LayerHub` to access all manager layers from one place.

## Maintenance
Regenerate grouping/copy plan via:
`python _curationTOOLS/organize_library_layers.py --root . --dest library --mode copy`

Apply updates via:
`python _curationTOOLS/organize_library_layers.py --root . --dest library --mode copy --apply`