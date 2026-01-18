Suggested structure:

Purpose & non-goals

“This layer owns sequencing, state, events, cancellation, retries.”

“It does not render UI; it does not contain widget code.”

Core objects

ForgeOrchestrator

ForgeConfig

ForgeState

ForgeEvent (typed events)

State machine

States: EMPTY, CARTRIDGE_SELECTED, SCANNED, INGESTED, REFINING, READY, ERROR, CANCELLED

Transition rules + allowed commands per state

Public API (this is the big missing piece)

select_cartridge(db_path)

scan(source, web_depth, binary_policy) -> ScanResult

ingest(selected_files, root_path) -> IngestStats

refine_step(batch_size) -> RefineStats

refine_until_idle(max_seconds=None)

validate() -> ValidationReport

export_artifacts(...) (optional)

cancel() / resume()

Event & telemetry contract

Event types: LOG, PROGRESS, STATE_CHANGED, ERROR, ARTIFACT_READY

Required fields, ordering guarantees

How UI subscribes (callback, queue, pubsub)

Concurrency & DB policy

“One write thread at a time”

Connection-per-operation vs persistent connection

Backoff strategy when locked

Batch write rules

Integration points

Intake service contract assumptions

Refinery contract assumptions

Neural service assumptions (embed model + dims)

Reference sequences

CLI sequence

GUI sequence

Resume-from-partial-cartridge sequence

This turns orchestration into a “stable spine” that the builder can target.
