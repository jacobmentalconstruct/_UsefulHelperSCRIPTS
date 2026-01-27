# RAGcartridgeFACTORY

## Executive Summary
**RAGcartridgeFACTORY** is a deterministic *datasource compiler* that converts arbitrary client datasets into a portable, self-contained **Neural Cartridge** (SQLite). The factory analyzes a source, compiles a human-checkable ingestion plan (registry), and executes that plan to produce a cartridge containing verbatim data, structured hunks, vector indices, and a knowledge-graph projection—along with a strict manifest that declares schema, provenance, and capabilities.

The factory does **not** reason over the data. Its sole responsibility is to *package* data so downstream agents (including small-context models) can reason efficiently and safely using explicit contracts.

---

## Core Principles (Non-Negotiable)
- **Compiler Model**: Analyze → Compile Plan → HITL Approve → Execute → Validate → Export.
- **Registry-Centered**: The registry is the source of truth; graph and vectors are projections.
- **Determinism First**: Verbatim truth is preserved; all derivations reference verbatim hunks.
- **Strict Contracts**: Manifest and schema define exactly what exists and how to query it.
- **HITL by Design**: Humans can inspect, tweak, and approve the plan before ingestion.
- **Factory, Not Agent**: No semantic interpretation or autonomous reasoning.

---

## System Boundary (What This App Is and Is Not)
**IS:**
- A compiler and packager for data
- A producer of deterministic artifacts
- A registry-driven ingestion and refinement engine
- A source of audit-grade build logs

**IS NOT:**
- A conversational agent
- A semantic interpreter of client data
- A decision-maker beyond configured rules
- A runtime inference system

---

## Contracts

### 1) Cartridge Contract (UNCF / RagFORGE Schema)
Defines tables, required columns, relationships, and queries. Guarantees:
- Verbatim storage with line-addressability and VFS paths
- Hunk trees with stable IDs and provenance
- Optional vector index keyed to hunks
- Optional graph projection keyed to registry items
- Self-describing manifest (schema, provenance, capabilities)

**Hard Rule:** Every derived artifact MUST reference a verbatim hunk.

### 2) Tool Contract
Defines how tools plug into the factory:
- **Inputs / Outputs**: Typed schemas
- **Side-Effects**: None | DB write | Manifest update | Filesystem write
- **Telemetry**: Structured logs + progress events
- **Phase**: Analyze | Plan | Commit | Refine | Validate | Export
- **Failure Policy**: Hard-fail | Fallback | Warn-and-continue

**Hard Rule:** Tools MAY NOT mutate prior artifacts outside their declared side-effects.

### 3) UI / Workbench Contract
Defines operator interaction:
- Panels/tabs with clear responsibilities
- Modal tools with size/location persistence
- Stepwise or chained execution
- Live telemetry/log inspection
- Explicit approval gates between Plan and Commit

---

## UX Contract v0.1 — Workflow, Tools, Telemetry, Logs

### Mental Model Exposed by the UI
The UI must make the following objects explicit at all times:
- **Source**: dataset root (filesystem path or URL root)
- **Plan**: compiled ingestion plan (registry snapshot)
- **Run**: one execution instance (timestamps + config hash)
- **Step**: a single tool invocation within a run
- **Artifact**: output produced by a step
- **Cartridge**: SQLite artifact being built

The operator must always be able to answer:
- What source am I operating on?
- What plan is about to execute?
- What step is running?
- What was produced and where is it stored?
- What failed or fell back?

### Workflow Workbench Panel
**Layout (stable 3-column pattern):**
- **Tool Library** (left): searchable; metadata popover
- **Workflow Chain** (center): ordered steps; enable/disable; per-step config
- **Artifacts Inspector** (right): structured summaries → drilldown

**Run Controls:** Dry Run, Run Step, Run From Step, Run All, Stop/Cancel, Reset Run

**Approval Gates:** Commit-phase tools require explicit Plan approval and show "Writes to Cartridge" warnings.

### Tool UX Requirements
Each tool must declare: phase, side-effects, inputs/outputs, failure policy.
Each step row displays: tool name, phase badge, side-effect badge, status, duration, output summary.

### Telemetry and Logging (Mandatory)
Two streams:
- **Thought Stream**: human-readable narrative of progress and decisions
- **System Log**: structured, persistent, filterable audit log

Severity levels: DEBUG, INFO, WARN, ERROR, CRITICAL.

Required events: StepStarted, Progress, Decision, ArtifactProduced, StepCompleted/Failed.

### Log Persistence
For each run persist:
- Run metadata (source, config hash, tool versions)
- Step inputs/outputs
- Full event stream
- Artifact references

Logs must be stored both locally and inside the cartridge.

### Modal Tools & Geometry Persistence
All modals must persist size, position, and relevant state. Outputs must also appear in the Artifacts Inspector.

### Plan vs Execution Separation
Plans are immutable snapshots. Commit tools must reference a specific plan ID.

### UX Acceptance Criteria
- All work attributable to run/step IDs
- No hidden side-effects
- Failures localized and explainable
- Exportable run report exists for every run

---

## Pipeline (Flowchart-Ready)
1. Source Select
2. Analyze
3. Compile Plan (Registry)
4. HITL Review
5. Commit Ingest (Verbatim/VFS)
6. Refine
7. Validate & Stamp
8. Export Cartridge

---

## Registry → Projections Model
- **Registry Items**: Files, hunks, entities, relationships (stable IDs)
- **Verbatim**: Exact content + line spans
- **Vector**: Embeddings keyed to hunks
- **Graph**: Optional projection of selected registry items

**Hard Rule:** The knowledge graph is a projection, not the contract.

---

## Microservices to Include (comma-separated)
CartridgeServiceMS, IntakeServiceMS, ScoutMS, ContentExtractorMS, RefineryServiceMS, ChunkingRouterMS, PythonChunkerMS, RegexWeaverMS, NeuralServiceMS, LexicalSearchMS, SearchEngineMS, ServiceRegistryMS, TkinterAppShellMS, TkinterThemeManagerMS, LogViewMS, TelemetryServiceMS, ThoughtStreamMS, TkinterSmartExplorerMS, NeuralGraphViewerMS

---

## App Layout Recipe
- **/src/app.py** – Entry point; config, service wiring, UI boot
- **/src/orchestrator.py** – Tool registry, workflow runner, plan compiler
- **/src/ui/** – Panels and modals:
  - Source Select + Explorer
  - Workflow Workbench
  - Logs
  - Thought Stream
  - Cartridge Inspector
  - Graph Viewer (optional)

---

## Build Guidance for Agents
- Build boilerplate first; no domain logic
- Enforce contracts before adding features
- Prefer explicit schemas over inference
- Log everything; print nothing
- Validate determinism with repeat runs

---

## Non-Goals
- No semantic interpretation of content
- No uncontrolled inference over client data
- No hidden schema assumptions

RAGcartridgeFACTORY is a *factory*, not an agent.
