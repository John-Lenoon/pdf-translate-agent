# Evaluation

## Golden Set

维护至少 30 个经人工确认的英文小说段落及参考中文译文，覆盖人物名、长距离上下文、对白、叙事语气、跨页段落、页眉页脚和边界排版。每条样本包含稳定 ID、来源 PDF hash、页码、segment ID 和人工备注。

## V1 process

1. 固定输入、模型 ID、Prompt 版本和上下文版本。
2. 运行翻译并保存原文、译文、Entity、Glossary 和渲染产物。
3. 人工抽样 Judge，记录问题类型、严重程度和备注；至少覆盖每章一个样本和所有渲染异常。
4. 对标记段落执行局部重译，再比较前后结果。
5. 任何质量回归都必须进入 issue 或 Golden Set 更新记录。

## Metrics

V1 以人工判断为主，重点观察上下文连贯性、忠实度、人物名一致性和 PDF 覆盖完整性。BLEU、COMET、BERTScore 等自动指标暂不作为发布门槛。

发布门槛：Golden Set 不得出现未记录的漏译、截断或缺字；人物名不得出现未经允许的 canonical 漂移；任何失败样本必须进入 `blocked` 或修复后重新评测。
