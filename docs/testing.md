# Testing Matrix

## Unit tests

- PDF AST page/block/line/span schema and stable IDs
- Natural paragraph splitting across page boundaries
- Entity normalization, SQLite uniqueness, transaction/upsert behavior
- User Glossary injection and structured model output validation
- Workflow state transitions, retry limits, cancellation and lease recovery
- Overlay layout, missing glyph, overflow and collision detection

## Integration tests

- A small digital-text PDF completes the full local workflow.
- Restarting the runner resumes without duplicate model calls.
- Manual Judge marks one segment and only that segment is retranslated.
- Source PDF hash change invalidates the run.

## UI checks

Verify progress, failed-page display, segment navigation, Entity display, Judge labels, retranslation action and artifact download with a local Next.js/FastAPI run.

## Evidence

Every completed roadmap item records the commands run, test result, fixture hash and any known limitations in the relevant version or ADR document.
