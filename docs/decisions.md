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
