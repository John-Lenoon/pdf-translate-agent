# V2 Product Discovery Notes

> Status: Historical. Superseded by [`../v2-dual-model.md`](../v2-dual-model.md). This file is retained for design-history reference only.

Date: 2026-09-02

## Opportunity

V2 must make local-first literary PDF translation cheaper than all-remote translation without hiding degraded review, exposing credentials, or making local setup too difficult. The target outcome is an unattended, inspectable PDF translation run for a user who has a local Ollama model and may choose to provide a remote-model key.

## Ideas by perspective

### Product management

1. Define a V2 scorecard: remote-review rate, remote tokens per page, pages per minute, render-failure rate, and developer preference between local and remote candidates.
2. Add an explicit run coverage classification: fully reviewed, locally accepted, or completed with review debt.
3. Gate default remote review behind Golden Set evidence rather than enabling it just because the route exists.
4. Define a supported-machine baseline before promising 50-page completion performance.
5. Version risk policies and report changes so a regression can be tied to a routing-policy change.

### Product design

1. Provide a local readiness screen that checks Ollama reachability, installed model, structured-output probe, available memory, and remote Profile status before accepting a PDF.
2. Show a concise run coverage report next to the download: local accepted, remote kept, remote revised, review debt, translation failures, and render failures.
3. Make review debt visually distinct from a successful remote review, including the specific continuation action available to a developer.
4. Provide a secret-safe Provider Profile flow: create, test, enable, rotate/delete; never redisplay a saved key.
5. Make artifact inspection navigable from the finished run, linking PDF pages to segment risk decisions and candidate history without restoring a normal-user Judge workflow.

### Software engineering

1. Treat Ollama as a true external dependency through `OllamaAdapter`; test `TranslationCoordinator` using a deterministic adapter, not a live model.
2. Establish a run-plan hash and validate it when resuming, so mismatched workflow/prompt/risk versions do not silently resume a historical run.
3. Make remote request idempotency explicit with a persisted dispatch key before a call, preventing duplicate paid reviews after a crash between provider response and SQLite write.
4. Enforce artifact retention and redaction: keep source/translation artifacts local, omit secrets and raw provider headers, and make old candidate cleanup deliberate rather than implicit.
5. Add contract tests for `run_report.json`, model-profile lifecycle, state transitions, and renderer input so V2 Modules remain independently testable.

## Prioritized experiments

| Priority | Idea | Why selected | Assumption to validate |
| --- | --- | --- | --- |
| 1 | Local readiness check | Avoids the most common failure: a user uploads a document before Ollama/model/Profile is usable. | A short preflight catches most configuration failures without materially delaying a run. |
| 2 | Run coverage report | Makes unattended routing trustworthy and exposes review debt without a user Judge loop. | Developers can diagnose quality/cost problems from aggregate counts plus artifact links. |
| 3 | Paid-call idempotency | A crash must not turn into duplicate remote-model charges. | Provider requests can be associated with a persisted dispatch key and reconciled safely. |
| 4 | Golden Set routing scorecard | Prevents a cost-saving design from degrading literary quality invisibly. | Developer preference data can calibrate a useful risk threshold. |
| 5 | Resume-plan validation | Protects reproducibility when Profiles or code versions change mid-run. | A clear mismatch state is safer than silently continuing with changed behavior. |

## Suggested experiments

1. Run the readiness check on the target machine with Ollama stopped, a missing model, an invalid structured response, and a valid model; verify stable user-visible errors.
2. Run a 10-page Golden Set through local-only and routed modes; compare remote-review rate, latency, tokens, and developer preference for each candidate pair.
3. Simulate a crash after a remote request is dispatched but before the translation record commits; verify recovery does not issue a duplicate paid request without an explicit reconciliation result.
4. Modify a Provider Profile after run creation, then resume; verify the immutable `RunModelPlan` is used or the run reports a plan mismatch.
5. Inspect a completed-with-review-debt report; verify a developer can identify debt segments, reason, and allowed continuation without opening raw SQLite files.
