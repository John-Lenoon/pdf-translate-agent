# Implementation Rules

本文档只规定执行方式；版本切片、验收条件和完成证据统一记录在 [`roadmap.md`](roadmap.md)。领域合同见 [`core-design.md`](core-design.md)，状态机见 [`workflow.md`](workflow.md)，验证命令见 [`testing.md`](testing.md)。

## Coding and module rules

- 翻译逻辑留在 Python；Next.js 只负责本地 review UI。
- 优先复用现有模块边界和最高测试 seam；不要为未批准需求添加抽象或基础设施。
- 代码、配置、API、数据结构、流程或用户行为变化时，同步检查受影响的唯一来源文档；测试数字只在 `testing.md` 维护。
- 真实模型和合法 fixture 才能作为端到端完成证据；mock 仅用于隔离单元测试。

## Escalation

每个切片先写输入、输出和验收条件；每轮修改立即运行最小验证。连续两轮无法缩小失败范围，或需要改变架构边界时，标记 `blocked` 并等待负责人决策；不得无限重试。V2 需求若未进入当前 roadmap 切片，标记 `deferred`。

## Governance

新增文档、架构边界、状态机、schema、凭据处理或渲染规则必须先更新相应 ADR/受控文档并按 [`review.md`](review.md) 判断是否需要独立审查。Git 操作遵循 [`git.md`](git.md)；Agent 不自动 commit 或 push。
