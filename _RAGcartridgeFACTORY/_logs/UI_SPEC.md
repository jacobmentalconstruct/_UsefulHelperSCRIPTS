Suggested structure:

UI goals

Visualize scan tree, ingestion selection, refinery progress, cartridge inspection, graph topology, neural test

Tabs / panels and their contracts

Data Ingestion tab: inputs, buttons, expected events, enabled/disabled rules by orchestrator state

Knowledge Inspector tab: expected DB read queries (file list, file view, chunk view)

Neural Topology tab: graph load, highlight results from neural test

UI ↔ orchestrator wiring

Which user actions call which orchestrator methods

Which event types update which widgets

Responsiveness rules

No long work on UI thread

Cancellation UX requirements

Minimal theming + layout constraints

Colors, fonts, spacing, docking, “safe defaults” for 1200x800 etc.
