# UiMAPPER

UiMAPPER is a local, Tkinter-based application that scans a Python project and builds a structured map of its UI surface area.  
It is designed as an orchestrated, microservice-driven system that separates UI, backend orchestration, and analysis logic into clean, composable layers.

The goal is to produce a reliable **UI map + callback graph + report artifacts** from an existing codebase without embedding business logic into the interface layer.

---

## Architecture Overview

UiMAPPER is intentionally split into three top-level components:

### 1) `app.py` — Dumb Shell
- Creates the Tk root
- Instantiates backend + UI orchestrators
- Starts the main loop
- Contains **no business logic**

### 2) `ui.py` — UI Orchestrator
- Owns:
  - Tkinter theme
  - layout
  - widgets
  - user interaction
- Subscribes to progress events
- Polls backend session state
- Displays:
  - run status
  - counters
  - logs
  - reports
  - decision plans
- Contains **no analysis logic**

### 3) `backend.py` — Backend Orchestrator
- Owns the entire pipeline lifecycle
- Wires microservices together
- Runs work off the Tk main thread
- Emits progress events
- Maintains authoritative run state

---

## Microservice Model

All non-orchestration logic lives in microservices.  
Backend composes them into a deterministic pipeline.

### Core runtime services

| Category | Services |
|---|---|
| Session | RunSessionStateMS, CancellationTokenMS |
| Events | ProgressEventBusMS |
| Errors | ErrorNormalizerMS |
| Discovery | GitignoreFilterMS, ProjectCrawlMS, PythonFileEnumeratorMS |
| Entry points | EntrypointFinderMS |
| AST | AstParseCacheMS |
| UI Mapping | AstUiMapMS, TkWidgetDetectorMS |
| Graphing | CallbackGraphBuilderMS |
| Unknown handling | UnknownCaseCollectorMS |
| Inference | InferencePromptBuilderMS, OllamaClientMS, InferenceResultValidatorMS |
| HITL | HitlDecisionRouterMS |
| Modeling | UiMapModelMS |
| Reporting | ReportWriterMS, ReportSerializerMS |

---

## Pipeline Flow


