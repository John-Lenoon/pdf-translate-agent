# AI Contract

## Model

V1 翻译使用 OpenAI-compatible API。正式 model ID 必须通过环境变量 `TRANSLATION_MODEL` 配置并写入每个 translation record；`OPENAI_BASE_URL` 可指向 DeepSeek 等兼容服务。API key 只从环境变量读取，不写入数据库或 artifact。

## Translation output

模型必须返回结构化 JSON：`translation`、`entity_observations`、`glossary_suggestions`、`warnings`。每个 entity observation 至少包含 `source_name`、`target_name`、`entity_type`、`evidence_text`。`entity_type` V1 只能为 `person`。Schema 校验失败时重试结构化请求；仍失败则将 segment 标记为 `failed`，不得把自由文本当作成功结果。

## Context

每个 segment 的上下文由章节摘要、邻近段落、当前人物 Entity 快照和用户 Glossary 组成。不得把整本小说无界限地注入单次请求；上下文必须记录 `context_version` 和来源 segment IDs。

## Entity

V1 只自动记录人物名。首次发现即写入当前 run 的 Entity Registry；后续命中同一 source name 时注入既有 target name。地点、组织、物品、别名和指代关系留到 V2。

## Glossary

只使用用户预先提供的 Glossary。模型建议可在翻译结果中返回并保存，翻译完成后供人工查看；建议不得暂停任务，也不得自动改变当前 run 的 Glossary。

## Review

V1 不调用模型 Judge。人工 Judge 在本地网页中标记问题类型和备注，Workflow 根据标记触发段落级重译。
