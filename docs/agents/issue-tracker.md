# Local Markdown Issue Tracker

本仓库没有远程 issue 服务时，Wayfinder 使用本地 Markdown 作为决策地图和 ticket 的持久化格式。

## Storage

- Canonical issue files live under `.wayfinder/issues/`.
- Each issue is one Markdown file named `<slug>.md`.
- The map issue uses the label `wayfinder:map`; child issues use one of `wayfinder:research`, `wayfinder:prototype`, `wayfinder:grilling`, or `wayfinder:task`.
- `.wayfinder/` is local planning state and must not contain secrets, source PDFs, translations, databases, or run artifacts.

## Front matter

Every issue starts with YAML front matter:

```yaml
---
title: "Decision title"
status: open
labels:
  - wayfinder:task
parent: null
assignee: null
blocks: []
blocked_by: []
---
```

Allowed `status` values are `open`, `in_progress`, and `closed`. `parent` points to the map filename. `blocks` and `blocked_by` contain issue filenames, not numeric IDs.

## Operations

- Create: add one issue file with a precise `## Question` section. Do not create a ticket for work that has no decision to resolve.
- Claim: set `assignee` to the current agent before editing or researching the issue.
- Block: add the blocking issue filename to `blocked_by` and add the reciprocal filename to the blocker's `blocks` list.
- Resolve: append a `## Resolution` section with the decision, evidence, and affected files; set `status: closed`.
- Map update: append one named link under `## Decisions so far` in the map. The map is an index and must not duplicate the ticket's full resolution.
- Frontier: open issues with `assignee: null` and an empty `blocked_by` list are available; choose them in map order.

## Naming and safety

Human-facing references use the issue `title`, with a relative Markdown link to the file. Never use a bare filename or invented numeric issue ID as the only reference. Keep one decision per ticket. Do not move or delete a closed issue; supersede it with a new ticket when the decision changes.
