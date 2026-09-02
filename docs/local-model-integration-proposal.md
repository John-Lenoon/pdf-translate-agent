# Local Model Integration Proposal

## Decision to Make

Use a local English-to-Chinese model as the default first-pass translator without
changing the existing PDF parsing, SQLite, Entity, review, or rendering contracts.
`qwen3:8b` served by Ollama is the first model to evaluate on the current Windows
machine. A cloud model is optional and must only receive explicitly selected
segments, never the full document by default.

This proposal is a V2 design discussion, not an implementation commitment.

## Opportunity

The current workflow has a strong per-segment boundary, but each paragraph and
chapter summary is paid for with a remote API. A 200-page document should increase
elapsed time and local artifacts, not GPU memory or proportional cloud cost.

```text
Outcome: affordable, private, resumable book translation
  ├─ Lower recurring model cost
  │   ├─ Local first-pass translation
  │   └─ Cloud calls only for selected review cases
  ├─ Preserve literary quality and name consistency
  │   ├─ Existing Entity and Glossary constraints
  │   └─ Targeted human/model review
  └─ Make long documents operable on one computer
      ├─ Bounded paragraph batches
      ├─ SQLite checkpoints and resume
      └─ Explicit local-model health and capacity feedback
```

## Ideas From Three Perspectives

### Product

1. **Local default, cloud optional**: Make local translation the normal route and
   present an optional paid review mode only when the user chooses it.
2. **Document budget estimate**: Before starting, estimate segment count, local
   runtime range, and the maximum number of cloud-review calls allowed.
3. **Quality tiers**: Offer Fast Local, Local + Human Review, and Local + Selected
   Cloud Review as named workflows rather than a hidden model setting.
4. **Run quality report**: Show translated, locally retried, human-flagged, and
   cloud-reviewed segment counts in the completed run.
5. **Golden Set gate**: Choose a local model only after it meets a fixed sample of
   narrative, dialogue, names, headers, and cross-page paragraphs.

### Design

1. **Provider readiness panel**: Show whether Ollama is reachable, the selected
   model is installed, and whether it is running on GPU or partly on CPU.
2. **Readable progress**: Report current page/paragraph, elapsed time, estimated
   remaining time, and the last durable checkpoint while translating.
3. **Review queue, not a full reader rewrite**: Retain the existing segment review
   view and add filters for warnings, long paragraphs, failed validation, and
   low-confidence candidates.
4. **Cost boundary disclosure**: Label any action that sends text to a cloud model
   with the exact segment count and provider, before it starts.
5. **Actionable failures**: Distinguish Ollama unavailable, model missing, malformed
   JSON, timeout, and render overflow; each failure should give a safe next action.

### Engineering

1. **Provider factory**: Replace the current OpenAI-named construction path with a
   configured provider factory while preserving the `TranslationProvider` protocol.
2. **Ollama adapter**: Use Ollama's OpenAI-compatible endpoint at
   `http://127.0.0.1:11434/v1`; model configuration and metadata remain explicit.
3. **Two-pass structured-output repair**: Request JSON once; on schema failure make
   one small repair request containing only the invalid output and schema, then fail
   the segment explicitly if validation still fails.
4. **Bounded local context**: Translate one natural paragraph at a time. Limit
   source/context token budgets and summarize chapters incrementally, never put a
   full book or full chapter into one request.
5. **Deterministic routing policy**: Start with local-only. Later, route a segment
   to a cloud reviewer only after an explicit, logged trigger such as a Judge flag,
   failed local validation, or a user-selected chapter review.

## Prioritized Five

| Priority | Idea | Why selected | Assumptions to validate |
| --- | --- | --- | --- |
| 1 | Provider factory + Ollama adapter | Smallest change: the workflow already depends on a provider interface. It immediately removes per-segment cloud cost. | Ollama's OpenAI-compatible Chat Completions and JSON mode work reliably with `qwen3:8b`. |
| 2 | Bounded local-first workflow | It keeps VRAM stable for 200 pages and preserves existing resume behavior. | Paragraph/context limits still yield acceptable literary coherence. |
| 3 | Local model readiness and explicit errors | A local service can be stopped, lack the model, or spill to CPU; invisible failures would make the tool feel broken. | Ollama health and model inventory can be checked quickly at run start. |
| 4 | Golden Set quality gate | Cost savings are meaningless if names, dialogue, or fidelity regress. | Thirty or more legally usable aligned examples can establish a practical baseline. |
| 5 | Targeted optional cloud review | It creates a quality escape hatch without returning to full-document API cost. | Human flags and deterministic validation rules identify enough of the risky passages. |

## Recommended Workflow

### Phase A: Local-only first pass

```text
Create run
  -> verify Ollama is reachable and qwen3:8b is installed
  -> parse PDF and segment it (existing behavior)
  -> create bounded chapter memory locally
  -> translate one segment at a time with Qwen3
  -> validate JSON, non-empty output, Entity and Glossary constraints
  -> persist SQLite record immediately
  -> render only after every segment is durable
  -> human Judge reviews completed output
```

The local model receives: current paragraph, a compact chapter memory, a fixed
number of neighbouring paragraphs, existing person-name mappings, and the user
Glossary. It does not receive the full PDF, full chapter text, or an unbounded
translation history.

### Phase B: Local automatic repair

Only for format or contract problems, retry locally with a stricter prompt:

```text
invalid/missing JSON or empty translation
  -> one local repair request
  -> valid structured result: continue
  -> still invalid: segment fails visibly and run can resume after correction
```

This is not a quality reviewer and must not silently replace a valid translation.

### Phase C: Optional selected cloud review

After local output exists, the user may select a chapter, Judge-flagged segments,
or a bounded sampling rate for review. Only those source/translation/context slices
are sent to a configured cloud reviewer. The reviewer returns a recommendation;
the system records which model produced the final text and why.

Cloud review must not be an automatic full-book fallback in the initial release.

## Proposed Configuration

Use provider-neutral names for the new path while retaining the old OpenAI variables
temporarily for backwards compatibility:

```env
TRANSLATOR_PROVIDER=ollama
TRANSLATOR_BASE_URL=http://127.0.0.1:11434/v1
TRANSLATOR_MODEL=qwen3:8b

# Optional, only for explicitly selected review work
REVIEWER_PROVIDER=
REVIEWER_BASE_URL=
REVIEWER_MODEL=
REVIEWER_API_KEY=
```

For Ollama, the API key value can be a non-secret placeholder required by the
OpenAI SDK; it must not be exposed to the web client. The integration should not
reuse `OPENAI_*` in user-visible labels or error messages.

## Capacity Guardrails for RTX 3070 8 GB

- Run a single translation request at a time.
- Start with a modest context window and cap the source plus context input.
- Keep chapter memory concise and persist it to artifacts rather than retaining a
  full book prompt.
- Check `ollama ps` during evaluation. Partial CPU offload is functional but makes
  runs markedly slower.
- Measure real time per segment on a 10-page sample before promising 50 or 200-page
  runtime estimates.

## Delivery Slices

1. Add provider-neutral configuration, Ollama health/model checks, an Ollama
   provider adapter, and focused unit tests using a fake compatible client.
2. Run a compatibility trial: one chapter summary and 20 representative segments;
   collect JSON validity, time per segment, GPU/CPU split, entity consistency, and
   manual Judge results.
3. Add bounded-context limits, a one-time local format repair, and a run report.
4. Evaluate the Golden Set against the current cloud baseline. Decide whether
   Qwen3 is sufficient for initial translation, and whether a reviewer is needed.
5. Only after those results, design the optional cloud-review queue and its UI.

## Explicit Non-goals for This Change

- No full-book prompt or persistent model chat session.
- No automatic full-document cloud fallback.
- No multi-model concurrent translation.
- No change to PDF rendering until model integration produces a verified output.
- No public deployment or hosted Ollama service.

## First Experiment

Before code integration, use Qwen3 in non-thinking mode with the exact structured
shape required by the workflow. Test 20 real but authorized segments, including
dialogue and person names, and record response time and JSON validity. Passing a
single prose sentence is useful for model setup, but insufficient evidence for
workflow adoption.
