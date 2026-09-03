# Evaluation

本目录是翻译质量迭代的唯一评测入口。任何会改变翻译行为、模型路由、Prompt、Entity/Glossary 规则、渲染质量或评测指标的代码或配置变更，都必须同步更新本文件，并按影响范围重跑对应评测。评测数据只允许使用用户拥有合法使用权的样本或脱敏元数据。

## Golden Set

维护至少 30 个经人工确认的英文小说段落及参考中文译文，覆盖人物名、长距离上下文、对白、叙事语气、跨页段落、页眉页脚和边界排版。每条样本包含稳定 ID、来源 PDF hash、页码、segment ID 和人工备注。

## V1 process

1. 固定输入、模型 ID、Prompt 版本和上下文版本。
2. 运行翻译并保存原文、译文、Entity、Glossary 和渲染产物。
3. 人工抽样 Judge，记录问题类型、严重程度和备注；至少覆盖每章一个样本和所有渲染异常。
4. 对标记段落执行局部重译，再比较前后结果。
5. 任何质量回归都必须进入 issue 或 Golden Set 更新记录。

## V2 dual-model process

V2 不在运行期间等待普通用户 Judge。评测由开发者在运行完成后比较本地候选、远程候选和最终选择，并把结论写入受控的 Golden Set 记录或脱敏评测结果中。

1. 固定输入 PDF hash、segment ID、模型 ID、Prompt 版本、context 版本和 risk-policy 版本。
2. 分别保存 local candidate、remote candidate（如触发）、最终选择、风险信号、review status 和 provider usage。
3. 对每个样本记录 `local_preferred`、`remote_preferred`、`tie` 或 `neither`，并记录忠实度、连贯性、Entity/Glossary、一致性和格式问题。
4. 统计 remote-review rate、remote tokens per page、local/remote latency、review debt rate、Entity violation rate、render failure rate 和 pages per minute。
5. 风险阈值或抽检比例变化前，先在同一 Golden Set 上比较旧策略与新策略；没有证据不得仅凭主观判断调高或调低阈值。
   当前默认策略为风险阈值 `0.35`、上下文降级权重 `0.35`、每 5 个段落抽检 1 个。可通过 `V2_REMOTE_RISK_THRESHOLD`、`V2_CONTEXT_DEGRADED_WEIGHT` 和 `V2_CALIBRATION_INTERVAL` 覆盖；每次覆盖都必须记录实际值和 `risk-policy` 版本。
6. 修改 Prompt、模型、分片策略、Entity 过滤或渲染逻辑后，必须重跑受影响类别，不能只运行单元测试代替质量评测。

渲染文字框扩展、字号/行距适配或 PDF 校验逻辑发生变化时，至少重跑边界排版、长译文、缺字、碰撞和输出文本完整性类别，并保留渲染失败率对比。

重排渲染（`V2_RENDER_MODE=reflow`）必须额外验证章节换页、中文字号、首行缩进、单一全局页码、图片/矢量地图区域和跨页文本完整性；Chromium 生成的页面至少抽样渲染为 PNG 进行人工视觉检查。Overlay 与 Reflow 的结果不得混称为同一版式策略。

每次重排评测还必须保留 `format_review.json`：每页的字号、墨迹比例、文本块数、嵌入图像数、截图和 segment 输出页映射；本地/远端格式审阅模型、usage、失败/债务；以及最多两次的章节级修复历史。确定性检查失败是硬门槛；模型审阅只补充视觉判断。格式审阅调用失败或超时必须记为 `format_review_debt`，不得计入已审核页。

## V2 benchmark record

实验性运行可以在没有完整基准时进行，但不得宣称正式支持 50 页。正式支持 50 页前，必须保留目标机器的基准记录，至少包括：GPU 型号和 VRAM、系统内存、Ollama 与模型/量化版本、context window、batch size、并发数、输入/输出 token、pages per minute、失败/重试率和峰值内存。基准记录可以是本地脱敏 JSON，但不得提交 API key、原始 PDF、完整译文或 SQLite/runs 产物。

## V2 coverage report

每次 V2 运行应能从 `runs/<run_id>/run_report.json` 或等价脱敏结果中回答：

- 总 segment 数，以及 local-only、remote requested、remote kept、remote revised、remote failed 和 review debt 数量；
- 每个 remote review 的模型、状态、输入/输出 usage 和失败原因；
- Entity/Glossary 冲突、未翻译文本、数字/标点异常和渲染失败数量；
- 当前 risk-policy、Prompt、context 和 model-plan 版本。

## Metrics

V1 以人工判断为主，重点观察上下文连贯性、忠实度、人物名一致性和 PDF 覆盖完整性。BLEU、COMET、BERTScore 等自动指标暂不作为发布门槛。

发布门槛：Golden Set 不得出现未记录的漏译、截断或缺字；人物名不得出现未经允许的 canonical 漂移；任何失败样本必须进入 `blocked` 或修复后重新评测。V2 还必须能解释远程审核覆盖率和 review debt，不能把未执行的远程审核报告为已审核。
