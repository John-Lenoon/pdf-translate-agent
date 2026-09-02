# Architecture Decisions

## ADR-001: Local-first V1

- Date: 2026-08-30
- Decision: V1 runs locally with Next.js, FastAPI, Python Workflow, SQLite, and filesystem artifacts.
- Rejected: Starting with PostgreSQL, queues, Kubernetes, or public deployment.
- Reason: Validate translation quality and PDF overlay correctness before operational scaling.

## ADR-002: Coordinate AST

- Date: 2026-08-30
- Decision: PyMuPDF coordinate AST is the internal document model.
- Rejected: Markdown/HTML as the canonical model.
- Reason: Original-page overlay requires span coordinates and page metadata.

## ADR-003: Person-only Entity V1

- Date: 2026-08-30
- Decision: Automatically persist globally unique person names per run.
- Rejected: Automatically persisting every noun or all named entities.
- Reason: Control table growth and avoid turning ordinary contextual words into hard constraints.

## ADR-004: Real-model first vertical slice

- Date: 2026-08-31
- Decision: The first implementation slice uses a real OpenAI translation call on a <=10-page digital-text PDF; mocks may be used only for isolated unit tests, never as end-to-end completion evidence.
- Rejected: A mock translation pipeline before provider integration.
- Reason: The primary risk is translation/context behavior, so the first end-to-end evidence must exercise the real provider contract.

## ADR-005: No vector database in V1

- Date: 2026-08-31
- Decision: V1 uses SQLite and filesystem artifacts only; no pgvector, Qdrant, or Milvus.
- Rejected: Introducing a vector database before retrieval quality and corpus size justify it.
- Reason: V1 context is limited to chapter summaries, neighboring paragraphs, person Entities, and user Glossary. These are deterministic, small, and directly addressable by segment/chapter IDs. A vector database would add embedding cost, indexing complexity, and another failure mode before it improves translation quality.
- Revisit when: V2 needs semantic retrieval across many documents, large translation memory, or measured retrieval failures that metadata/keyword lookup cannot solve.

## ADR-006: V2 local-small-model and remote-large-model cascade

- Date: 2026-09-02
- Decision: V2 uses a local small model for initial structured translation. Deterministic QE and bounded risk scoring route only high-risk segments to a user-configured remote large model for keep/revise review. A valid remote revision may be selected automatically; developers review completed PDF/run artifacts after the run, not during it.
- Rejected: A single remote large model for every segment; a fixed three-model pipeline; full-PDF remote review; generic vector RAG; ordinary-user Judge selection in the V2 workflow.
- Reason: Local initial translation lowers remote token cost. A bounded local context package and deterministic validation protect consistency and traceability without making the first run interactive. Larger models are evaluated rather than assumed superior.
- Security: The local app has Provider Profiles, not user accounts. API keys live in the operating-system credential vault and are referenced, never stored, by SQLite or run artifacts.
- Storage: SQLite remains the V2 store. PostgreSQL is deferred until a separately approved remote multi-user service requires it.
- Details: [`docs/v2-dual-model.md`](v2-dual-model.md).
