---
title: "Consolidate project documentation"
status: closed
labels:
  - wayfinder:task
parent: null
assignee: null
blocks: []
blocked_by: []
---

## Problem Statement

项目文档对模型合同、V2 双模型、PDF 渲染、API 字段、数据库字段和实施切片存在重复维护，且部分链接、白名单和 V2 凭据说明不一致。

## Solution

建立单一核心设计规范，删除重复规范，把实现细节交给代码、Pydantic、迁移和测试；其余文档只保留各自职责范围。

## User Stories

1. As a project maintainer, I want one source for model, routing, rendering, and failure principles, so that design changes do not require synchronized copies.
2. As an implementer, I want API and database details generated from code, so that documentation cannot drift from runtime contracts.
3. As a reviewer, I want roadmap, workflow, and testing to have distinct responsibilities, so that acceptance evidence is easy to locate.
4. As a user, I want README instructions to describe only supported V1 operations, so that incomplete V2 configuration is not presented as usable.

## Implementation Decisions

- 合并模型、V2 路由和渲染原则为唯一核心设计规范。
- 删除被合并的旧规范，不保留兼容别名或重复历史副本。
- API 字段和 Schema 以 FastAPI/Pydantic 自动生成的 OpenAPI 为真值。
- 数据库字段和迁移细节以下层代码为真值，文档只维护关系、策略和不变量。
- 实施文档只维护编码、模块、升级和阻塞规则；版本切片与验收归路线图。
- 修正文档白名单、索引和所有旧链接；README 不描述未完成的 V2 凭据流程。

## Testing Decisions

- 运行 Markdown 链接扫描，确保相对链接均指向存在文件。
- 运行 `git diff --check` 检查文档格式。
- 扫描仓库，确保已删除规范名称不再被正式文档引用。

## Out of Scope

- 不修改翻译逻辑、API 实现、数据库 schema 或前端行为。
- 不新增远程 issue 服务、认证、部署基础设施或 V2 未完成能力。

## Further Notes

该决策将文档维护责任集中到受控文档地图，并保留 Git 历史作为被删除规范的追溯记录。

## Resolution

已完成核心规范合并、旧文档删除、API/数据库/实施文档精简、README V2 说明修正及链接和治理白名单同步。Markdown 链接扫描和 `git diff --check` 已通过。
