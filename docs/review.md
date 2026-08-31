# AI Code Review Policy

## Roles

- Terra：按当前 slice 实现代码、测试和文档变更。
- Sol：只对核心疑难问题和高风险边界进行独立 review，不对所有改动做全量审查。
- 项目负责人：确认 review 结论、处理 `blocked` 决策，并决定是否接受变更。

## Review triggers

必须请求 Sol review 的改动包括：

- 改变模块边界、Workflow 状态机或版本验收条件
- 修改 SQLite schema、migration、Entity 唯一性、lease/heartbeat 或 Idempotency 逻辑
- 修改 PDF AST、自然段切分、坐标映射、字体、覆盖、overflow 或碰撞检测
- 修改 Prompt、结构化输出 schema、上下文组装、模型路由或重译策略
- 修改文件权限、路径校验、密钥处理、数据删除或第三方 API 数据流
- 修复 Golden Set 回归、跨页段落、人物一致性或不可复现的质量问题
- 引入新依赖、改变锁文件、升级核心运行时或改变部署方式
- 任何影响多个模块或无法由单元测试充分证明的改动

## Review usually not required

以下改动通常由 Terra 自测即可，不要求 Sol 全量 review：

- 纯格式化、拼写、注释和文档措辞调整
- 不改变行为的局部重命名或机械重构
- 已有模式下的简单 UI 文案或样式调整
- 单元测试补充，且不改变被测接口和生产代码行为
- 已经通过同一 slice review、仅修复 review 指出的机械性问题

如果这些改动组合后跨越多个模块，仍按高风险改动处理。

## Review scope

Sol 的 review 只回答四类问题：

1. 是否违反 `AGENTS.md`、当前 ADR 或 V1 验收条件。
2. 是否引入数据丢失、重复扣费/调用、任务无法恢复或结果不可追溯。
3. 是否破坏 PDF 页面、文字、字体、坐标或中文可读性。
4. 是否存在测试覆盖缺口，导致核心质量回归无法被发现。

Sol 不负责重新实现功能、不做全仓库风格审查，也不替代运行测试。

## Review packet

请求 review 时只提供：变更目标、涉及文件、相关 ADR/验收条件、测试命令和已知风险。优先审查最小 diff，不要求 Sol 阅读无关历史。

Review 输出按严重程度列出问题：`blocker`、`high`、`medium`、`low`，每条包含文件、证据、影响和建议。没有核心问题时明确写 `No blocking findings`，并列出未覆盖的剩余风险。

## Resolution

- `blocker`/`high`：不得将 slice 标记为 `completed`，Terra 需要修复后重新 review。
- `medium`：记录为当前 slice 风险；是否修复由项目负责人决定。
- `low`：可进入后续 backlog，不阻塞交付。
- 连续两轮 review 未减少问题范围时，标记 `blocked` 并等待人工决策，不继续无边界修改。
