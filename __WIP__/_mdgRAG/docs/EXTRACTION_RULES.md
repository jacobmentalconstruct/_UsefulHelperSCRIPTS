# Extraction Rules

## Core Principle

The legacy project is **source material only**. Whole scripts are never
transplanted. Only narrow, well-bounded units are extracted and re-homed under
correct ownership in the new scaffold.

## What May Be Extracted (One at a Time)

- A pure helper function (no side effects, no global state)
- A small dataclass or typed container
- A narrow algorithm with clear inputs and outputs
- An isolated utility (hashing, normalization, formatting)

## What May NOT Be Extracted

- An entire legacy script or module
- A function that touches multiple ownership domains
- A class that mixes storage, UI, and business logic
- Anything with unclear ownership — leave it for a later phase

## Extraction Protocol

For every extraction:

1. Identify the source file and function/class name in the legacy project
2. Determine the single owner module in the new scaffold
3. Rewrite the unit cleanly — do not paste legacy code verbatim
4. Add a provenance comment: `# Extracted from: <legacy_file> :: <function_name>`
5. Record the extraction in `src/adapters/legacy_source_notes.md`
6. Verify the new module still imports and passes tests

## Ownership Rule

Every extracted unit belongs to **exactly one** owner module. If a function
logically spans multiple domains (e.g., it scores AND hydrates), it must be
decomposed before extraction.

## Adapter Layer

The `src/adapters/` directory exists for temporary compatibility shims during
migration. Adapters are **not** the final destination for extracted logic. They
are bridges that will be removed once migration is complete.
