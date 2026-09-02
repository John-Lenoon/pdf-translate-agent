# V2 Dual-Model Translation Design

## Status

`planned`. This document records the accepted V2 direction. It is not implementation evidence and does not change the V1 acceptance criteria.

## Terms

| Term | Meaning |
| --- | --- |
| candidate | A versioned segment translation produced by a local or remote model; it is not necessarily selected for rendering. |
| current candidate | The candidate currently selected by the `TranslationCoordinator` after validation. |
| final translation | A current candidate that the coordinator has settled and the `RunFinalizer` may render. |
| settled | All required translation, validation, ordered Entity merge, and routing work for a segment has completed. A segment with a translation failure is not settled. |
| unresolved | A coordinator-detected inconsistency, such as a stale Entity snapshot, that has not yet been retried or converted to a segment error. It cannot render. |
| review debt | A valid local final translation whose required remote review did not run or did not complete because of a limit or credential/provider condition. |
| pass | One attempt to reach a terminal run result. `completed_with_review_debt` ends a pass but may be explicitly continued later. |

## Goal

Reduce remote-model cost without making the first translation run depend on human decisions. V2 keeps the local-first, digital-text English-to-Chinese literary-PDF scope and introduces a two-model cascade:

```text
PDF -> coordinate AST / document IR -> preprocessor -> paragraph batches
     -> local small-model translation -> deterministic QE / risk score
     -> low risk: accept
     -> high risk: remote large-model review or revision
     -> validated translation -> overlay rendering -> translated.pdf
```

The small model is local only. The large model uses a user-configured compatible Provider and is called only for high-risk segments. A remote model never receives the complete PDF merely to review one segment.

## Boundaries

- Keep SQLite and local filesystem artifacts. PostgreSQL, accounts, hosted multi-user operation, queues, and public deployment remain V3 work.
- There is no login page in the local app. A user may create local Provider Profiles, but these are not user accounts.
- Do not store an API key in SQLite, `runs/`, logs, artifacts, browser persistent storage, Prompt snapshots, or error reports. Store the key in the operating-system credential vault; SQLite stores only an opaque credential reference.
- V2 has no user-facing budget configuration screen. The runner still records remote token usage and applies internal safety limits.
- Do not introduce a vector database or generic RAG. Context comes from chapter summaries, adjacent paragraphs, Entity and Glossary snapshots, and bounded structured lookup within the current run.
- Do not add OCR, table-specialist models, formula/code routing, cross-document fuzzy Translation Memory, or a middle-model tier to V2.
- V2 does not expose a normal-user Judge workflow. Developers inspect final PDFs and `runs/` artifacts; automated translation never waits for a human choice.

## Core modules

V2 keeps orchestration complexity behind three deep Modules. The Workflow runner calls these Modules; repositories persist their results but do not reproduce their decisions.

### `TranslationCoordinator`

Its Interface accepts a run's immutable model plan and ordered document segments, then produces settled translation candidates and Entity decisions. It owns batching, bounded local-model concurrency, dependency-aware context assembly, provider invocation, retries, and ordered Entity merging.

The coordinator may translate independent batches concurrently, but it must create an ordering barrier before a batch reads Entity data introduced by an earlier ordinal range. If a completed candidate used a stale Entity snapshot, the coordinator must retranslate it with the current snapshot or convert it into an explicit segment error; it must never silently treat it as consistent. Callers do not schedule Entity writes or decide which batch is safe to start.

### `QualityRouter`

Its Interface is `decide(candidate, translation_context) -> RoutingDecision`. `translation_context` may contain only source/neighboring segments, chapter summary, Entity snapshot, user Glossary, validation results, retry history, and declared structural flags. It must not expose a repository, Provider Profile, API key, token balance, or renderer state. The Module owns deterministic checks, the small-model risk label, risk scoring, thresholds, and routing reason. A `RoutingDecision` contains the score, signals, route, and review requirement; its persistence is an audit record, not an input that other Modules reinterpret.

### `RunFinalizer`

Its Interface accepts settled translations and produces a terminal run result and artifacts. It owns page readiness, rendering dispatch, final PDF staleness, and the distinction between render failure, full completion, and review debt. It calls the renderer only with a page AST and final translations; the renderer never reads Entity state, risk scores, Provider Profiles, or run status.

## Document IR and segmentation

PyMuPDF's versioned coordinate AST remains the canonical document IR. Docling-derived structure may help prepare model context, but it must not replace the AST-to-render mapping.

1. Extract stable natural-paragraph segments with page/span/bbox references.
2. Never split a sentence merely to meet a token limit. A long paragraph may split only at sentence boundaries and must retain parent/child identifiers.
3. Form requests from contiguous paragraphs within the same chapter. Batch size is constrained by the local model's configured input/output token limits, not by PDF page boundaries.
4. Supply a bounded context package: chapter summary, neighboring paragraphs, current Entity snapshot, and user Glossary. Record source segment IDs and `context_version`.
5. Preserve page headers, footers, and repeated text in the output. Repeated text may be translated once and mapped to all occurrences; it must not be silently skipped.

The preprocessor may bypass model calls only for content that must remain unchanged, such as page numbers, URLs, email addresses, pure numeric strings, and pure symbols. Each bypass must retain a reason in the segment metadata.

## Model interaction and selection

The local small model returns the existing structured translation contract plus a bounded, explainable risk label. It may run bounded independent batches concurrently, subject to its Model Profile. Entity observations from concurrent work must be merged in document ordinal order; request completion order must never decide the canonical translation of a person's first appearance.

The risk score combines deterministic checks and the small-model risk label. Deterministic signals include malformed structured output, empty translation, Entity or user Glossary conflict, missing numbers, anomalous length, context degradation, retry history, and configured structural cases such as cross-page paragraphs or dialogue.

Low-risk translations become the current candidate automatically. For a high-risk segment, the remote large model receives only:

- source segment and local candidate;
- chapter summary and neighboring source/translation context;
- Entity and user Glossary constraints;
- a request for `keep` or a structured revision, reasons, warnings, and observations.

A remote revision replaces the local candidate only when it passes the same JSON, completeness, Entity, Glossary, and length validation. Otherwise preserve the valid local candidate and record `review_debt`; never silently claim that segment received successful remote review. Store both candidates, selection reason, model IDs, Prompt version, context version, usage, and timestamps.

Each segment must persist the `RoutingDecision` output as a `risk_decision` record containing `score`, deterministic `signals`, small-model `risk_label`, `route` (`local_only` or `remote_review`), `review_status`, and `selection_reason`. `review_status` is one of `not_required`, `kept`, `revised`, `review_debt`, or `failed`. This record is the evidence for threshold tuning and developer review; no other Module recalculates it.

This is unattended automation: no human chooses between candidates during a run. Developer review after completion supplies evaluation evidence but is not an automatic decision source.

## Provider and resource profiles

Local Model Profiles define the Ollama endpoint, model ID, quantization/build metadata when available, context window, maximum generation tokens, batch concurrency, and retry limits. A local `OllamaAdapter` verifies that the endpoint is reachable, the named model exists, and the configured structured-output contract is supported before a run starts. The support check uses a fixed, minimal probe request and succeeds only when the response parses and validates against the configured schema. It emits stable errors including `local_model_unavailable`, `local_model_not_found`, and `local_model_contract_unsupported`. Local tokens are recorded for performance analysis, but are not a monetary run budget.

Remote Provider Profiles define the compatible base URL, model ID, credential-vault reference, maximum concurrency, and known request limits. The API must never return the secret value to the browser. A run stores the profile/version reference, not the key.

The Provider Profile lifecycle is `draft`, `tested`, `enabled`, and `deleted`. A profile becomes `enabled` only after a local connection test succeeds. If a credential is deleted or cannot be resolved when a runner resumes, the runner must stop remote review and report `provider_credential_unavailable`; it must not fall back to an environment key or attempt anonymous calls. Deleting a profile must preserve existing run records while making the credential reference unusable.

At run creation, the API resolves enabled profiles into an immutable, secret-free `RunModelPlan`: local and remote adapter type, endpoint, model ID, model/profile version, request limits, prompt/workflow version, risk-policy version, and credential-vault reference. The profile can change later without changing an existing run. On recovery the runner reads only this plan and resolves its credential reference at dispatch time; no API key is stored in the plan.

For remote calls, estimate input and reserve output tokens before dispatch, then record actual provider usage. A soft threshold stops new optional remote-review work; a hard per-run limit stops further remote calls with a `budget_exceeded` event and list of affected segments. Local translation may complete where valid. These limits protect a user's own key and guard against routing or retry failures; they are not a billing feature.

The V2 state-machine extension is:

```text
translating -> rendering -> completed | completed_with_review_debt | render_failed
completed_with_review_debt -> remote_review_queued -> translating
```

`completed_with_review_debt` is a resumable terminal state for the current pass and may expose a valid translated PDF. Explicit developer continuation after credentials or limits are restored queues only debt segments. Any revised final translation makes the prior PDF stale and requires the affected pages to render again. A missing credential while debt remains is reported as `provider_credential_unavailable`; it never changes settled local translations.

## Rendering and developer review

Parsing and translation may pipeline after dependencies are ready. A page is eligible for final overlay rendering only after all of its segments are settled, all relevant Entity decisions have been merged in document order, and no segment has a translation failure. Existing missing-glyph, overflow, collision, page reopen, and text-extractability checks remain release gates.

The developer review surface is the final `translated.pdf`, structured candidate history, risk decisions, risk reasons, and render errors stored under `runs/<run_id>/`. The stable entry point is the versioned `runs/<run_id>/run_report.json`. It must contain `schema_version`, run status and permitted next actions, model-plan reference, per-segment source/candidate references, `risk_decision`, selection status, Provider events and usage, `review_debt`, render validation results, and artifact paths. Write it through temporary-file atomic replacement; on recovery, regenerate it from canonical SQLite records and validated artifacts. It must separate translation-review outcomes from rendering failures. V2 removes the ordinary-user Judge UI from the product flow; developer-only targeted retranslation may remain available through local developer tooling.

## Evaluation and rollout

Before enabling remote review by default, run the V1 Golden Set and record for each segment whether the local candidate, remote revision, or neither is preferred by the developer reviewer. Measure remote-review rate, remote token use, latency, Entity/Glossary violations, render failures, and developer-reported fidelity/coherence/formatting issues.

Before choosing default local concurrency or batch limits, produce a benchmark artifact for the target machine. It records GPU model and VRAM, system RAM, Ollama and model/quantization version, context window, batch size, concurrency, input/output tokens, pages per minute, failure/retry rate, and peak memory use. Do not claim 50-page performance before this evidence exists.

Only adjust risk thresholds using recorded evidence. Do not assume a larger model is always better, and do not introduce generic RAG without measured cross-chapter failures that the structured context cannot resolve.
