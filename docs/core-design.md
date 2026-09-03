# Core Design

本文档是模型、上下文、双模型路由和 PDF 输出的唯一设计规范。代码中的类型、Schema、函数接口和测试是实现细节的真值。

## Principles and boundaries

- V1/V2 均是本地优先的英文到中文数字文本 PDF 翻译；原 PDF 永不修改，输出独立中文阅读版。
- V1 使用 OpenAI-compatible Provider；V2 先由本地 Ollama 小模型初译，再按风险将高风险段落发送给远程大模型审校或修订。
- SQLite 和本地文件系统是 V1/V2 的存储边界；不引入托管队列、PostgreSQL、OCR、通用 RAG 或多租户服务，除非 ADR 批准。
- V1/V2 只自动管理人物 Entity。用户 Glossary 必须应用；模型 Glossary 建议只保存供运行后查看，不阻塞或改变当前运行。
- 首次翻译无人值守。V1 的人工 Judge 在完成后触发段落级重译；V2 首轮不等待普通用户选择，开发者审阅 PDF 和运行产物。

## Model contract

模型返回结构化结果，至少包含译文、人物 observations、Glossary suggestions 和 warnings；V2 本地模型还返回受限风险标签。Schema 校验失败按 Workflow 重试，最终失败必须标记 segment error，不得把自由文本当作成功。

上下文只包含章节摘要、邻近段落、当前 Entity 快照、用户 Glossary、验证结果和结构标记，并记录 `context_version` 及来源 segment IDs；不得无界限注入整本小说。

## V2 routing

`TranslationCoordinator` 负责本地初译、远端候选审阅和按文档顺序的 Entity 合并。`QualityRouter` 独占确定性检查、风险评分、阈值和路由理由。Workflow 在所有有效译文就绪后调用渲染器。

低风险候选自动采用。远程审校只接收源段落、本地候选和有界上下文；远程修订必须通过相同的 JSON、完整性、Entity、Glossary 和长度校验，否则保留有效本地候选并记录 `review_debt`。候选、风险决策、模型计划、Provider 事件和运行报告必须可追溯；Provider 配置不写入 run artifact 或报告。

## Rendering contract

阅读版渲染器从 AST 组织章节流，使用 Chromium 在原纸张尺寸上重新分页；中文可增加页数，正文固定为 13pt，不得为塞入原页而缩小。图片直接提取，矢量地图/图表以源页区域截图保留，并按原页纵向上下文插入。章节分别渲染后由 PyMuPDF 合并，并写入单一全局中文页码。

中文字体必须验证 glyph 覆盖。每页渲染后检查 PDF 可重开、文字可提取、segment 完整、最小正文字号、空页和正文碰撞；报告每页尺寸、墨迹比例、文本块数、图像数和 PNG 截图。缺字、截断、碰撞、不可读页面或源文件变化均使 run 失败；不得生成伪成功 PDF。

本地格式模型审阅每个输出页；确定性异常、可疑页或本地失败才调用远端视觉模型。调用失败或超时形成 `format_review_debt`，远端确认失败最多重排受影响章节两次。`format_review.json` 必须保留审阅事件、usage、页映射、结构判断和修复历史。

## Failure and recovery semantics

translation failure、未解决 Entity 一致性问题和渲染验证失败必须显式记录，不能静默跳过。取消、崩溃、API 重启或失租后，runner 依据 SQLite 状态和 artifact hash 恢复；有效译文不得重复调用模型。任何修订后的最终译文都会使受影响页面的旧 PDF 失效并要求重新渲染。

ADR、评测证据和 roadmap 记录选择理由、版本状态和发布门槛；本文件不复制切片清单或测试数字。
