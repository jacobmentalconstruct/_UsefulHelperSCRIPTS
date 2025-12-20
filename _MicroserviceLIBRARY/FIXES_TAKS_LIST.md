Yep. Here’s a **save-able tasklist** to get `_MicroserviceLIBRARY` back into a clean, “graph-mappable microservice injection library” state, starting from the current hard failure.

## Tasklist: Fixes to stabilize + make services graph-ready

### Phase 0 — Unblock the current crash (TESTME.py)

* [ ] **Fix `service_metadata()` signature mismatch**: your services pass `dependencies=...` (and possibly other fields) into `@service_metadata(...)`, but the decorator currently only accepts `(name, version, description, tags, capabilities=None)` and will throw on unknown kwargs. 
* [ ] Choose one approach and apply consistently:

  * [ ] **Option A (recommended):** extend `service_metadata()` to accept optional fields like `dependencies`, `side_effects`, `inputs_schema_version`, etc (store them in `_service_info`).
  * [ ] **Option B:** remove `dependencies=` from all decorators and store dependency info elsewhere (less ideal because you already rely on it in multiple services). Example where it’s used now: 

---

### Phase 1 — Make the repo “import-clean” (many files look syntactically broken)

These will prevent crawling, importing, and schema extraction.

* [ ] **Run a formatting/parse pass and fix indentation defects** (a lot of classes/methods are left-flush when they should be indented). Example: `ChunkingRouterMS.__init__` is not indented under the class. 
* [ ] **Fix outright syntax errors** that will stop Python parsing:

  * [ ] `__PythonChunkerMS.py` contains invalid constructs like `@dataclass PythonChunkerMS CodeChunk:` and `PythonChunkerMS PythonChunkerMS:` which won’t parse. 
* [ ] **Add a “repo parse gate” script**: walk all `__*MS.py` files and `ast.parse()` them; report failures with filename + line number (this becomes your first automated health gate before TESTME even runs).

---

### Phase 2 — Standardize the service contract (so agents + graph tools can rely on it)

* [ ] **Enforce one metadata schema** for every service:

  * [ ] required: `name`, `version`, `description`, `tags`
  * [ ] optional: `capabilities`, `dependencies`, `side_effects`
* [ ] **Enforce one endpoint schema**: `inputs`, `outputs`, `description`, `tags`, `side_effects`, `mode` (these already exist in `service_endpoint`). 
* [ ] **Add a “service self-check endpoint” convention**: `get_health()` returning `status/uptime/...` (you’ve started doing this in places like ContentExtractorMS). 

---

### Phase 3 — Dependency handling (installability + graceful degradation)

* [ ] **Normalize dependency strategy**:

  * [ ] Either: “declare in metadata only” (preferred for graph mapping), and let installers handle it
  * [ ] Or: runtime dependency check blocks (some files do this), but standardize the messaging + behavior
* [ ] **Make dependency behavior consistent with metadata** (example: ContentExtractorMS lazily imports PDF/HTML libs and reports readiness). 

---

### Phase 4 — Make everything graph/db mappable

* [ ] **Expand `extract_service_schema()` output** to include:

  * [ ] `meta.dependencies` (after Phase 0)
  * [ ] `meta.capabilities`
  * [ ] `endpoints[].side_effects`
* [ ] **Add an ID convention** for nodes: `service:{name}` and `endpoint:{service}.{endpoint}` (stable keys)
* [ ] **Add a “graph export” function/script**:

  * [ ] exports JSON nodes/edges from all services using `extract_service_schema()`
  * [ ] edges like: `service -> endpoint`, `service -> dependency`, `service -> capability`

---

### Phase 5 — Build the “crawler that corrects the list of issues”

(This matches your earlier idea: crawl services and produce a reliable issues list.)

* [ ] Create `crawl_services.py` that outputs:

  * [ ] Parse errors (AST parse)
  * [ ] Import errors (attempt import in isolated try)
  * [ ] Decorator/schema extraction errors (call `extract_service_schema`)
  * [ ] Contract errors (missing required metadata fields, missing required endpoint keys)
  * [ ] Dependency declaration mismatches (metadata says dependency but no runtime guard, or vice versa)
* [ ] Output format:

  * [ ] JSON report (`service_issues.json`)
  * [ ] readable markdown summary (`service_issues.md`)
* [ ] Add a strict mode: `--fail-on critical` (parse/import errors)

---

### Phase 6 — Tests (so regressions stop happening)

* [ ] Add `tests/test_parse_all.py`: every service file parses
* [ ] Add `tests/test_schema_extract_all.py`: every service extracts schema
* [ ] Add `tests/test_contract_minimums.py`: name/version/description/tags always present

---

### “Is anything missing from the dump?”

Based on the tree, you have the service modules plus `microservice_std_lib.py`, `base_service.py`, and some utilities. 
What I **don’t** see in the dump (but you may intentionally omit) is:

* [ ] a `requirements.txt/pyproject.toml` describing the optional deps (networkx, pydantic, pywebview, bs4, pypdf, etc.)
* [ ] a single “runner” entrypoint for crawling/tests (unless `TESTME.py` is that)

If you want, I can turn the above into a **`TASKLIST_microservice_library.md`** format (checkbox-ready) next, but this should already paste cleanly into your system.
