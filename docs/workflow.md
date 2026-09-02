# Translation Workflow

## V2 extension

V1's state machine and user-facing Judge contract remain its acceptance baseline. V2 replaces ordinary-user Judge interaction with unattended dual-model routing and developer artifact review; the V2-specific design is [`v2-dual-model.md`](v2-dual-model.md).

```text
translating -> rendering -> completed | completed_with_review_debt | render_failed
completed_with_review_debt -> remote_review_queued -> translating
```

`completed_with_review_debt` is a resumable terminal state for a pass. It may expose a validated PDF, but the run report must identify each segment whose required remote review is outstanding. Explicit developer continuation queues only those debt segments. A translation failure or unresolved Entity consistency issue prevents the affected page from rendering; a render validation failure remains `render_failed`.

V2's `TranslationCoordinator` owns batching, retrying, local/remote model invocation and ordered Entity merging. `QualityRouter` is the sole owner of risk routing. `RunFinalizer` decides page readiness and invokes the renderer only with final translations. Details and Interfaces are defined in the V2 design document.

## State machine

```text
created → parsing → parsed → segmenting → segmented
                                      ↓
                                  translating
                                      ↓
                                   rendering
                                      ↓
                           completed / render_failed

任何活动状态 → cancel_requested → cancelled
任何活动状态 → failed
completed → reviewing → retranslate_queued → translating
```

首次翻译无人值守。人工 Judge 只在 `completed` 后运行，不阻塞首次翻译。

## Steps

1. 校验 PDF 类型、大小和可提取文本比例，计算源文件 hash。
2. 使用 PyMuPDF 生成版本化 AST，保留 page、block、line、span、bbox、字体和图片引用。
3. 按自然段生成稳定 segment ID，并保留 segment 到 span 的映射。
4. 维护章节摘要、邻近段落上下文和全书人物 Entity 快照。
5. 调用翻译 Provider，返回结构化译文和人物观察结果。
6. 写入 SQLite 和 run artifacts，支持幂等恢复。
7. 在原页面遮盖原文区域并绘制中文译文，执行碰撞和 overflow 检查。
8. 本地网页展示原文、译文、上下文和产物；人工标记后只重译目标段落。

## Chapter context

章节摘要在章节首次进入翻译前生成一次并保存为 artifact；后续 segment 只读取该摘要、前后邻近自然段和当前 Entity 快照。摘要生成失败不阻塞解析，但必须标记为 `context_degraded` 并在运行报告中显示。

## Entity concurrency

并行 segment 返回的人物 observation 先进入写入队列，由单一 runner 事务合并到 SQLite。首次出现的 `source_name` 直接建立 canonical Entity；后续 observation 只能复用，不得覆盖。

## Review UX contract

网页必须支持按页或 segment 查看原文、译文、前后文和 Entity；Judge 可选择 `ok`、`fidelity`、`coherence`、`entity`、`formatting`、`other` 并填写备注。提交后只将该 segment 加入重译队列。

## Retry rules

瞬时 Provider 错误（网络、限流、临时服务错误）最多自动重试 3 次并指数退避；不可重试错误立即失败。人工 Judge 触发的重译不设固定次数，但每次必须有新的 Judge 反馈或上下文变更，并受运行预算限制；没有新证据时停止并标记 `blocked`。所有重译必须保存原因、attempt、模型、Prompt 和上下文版本；不得无限循环。

取消、进程崩溃或 API 重启后，runner 根据 SQLite 状态和 artifact hash 恢复；已存在且校验通过的 translation 不得重复调用模型。

AST、Glossary、章节摘要及派生 JSONL artifact 使用临时文件原子替换。模型 warnings 和 Glossary suggestions 先与 translation metadata 同事务保存，再从当前 translation 记录幂等物化，避免提交后崩溃造成丢失。运行取消优先于普通 Provider 或 render error；失去 lease 的 worker 不得改变后续状态。
