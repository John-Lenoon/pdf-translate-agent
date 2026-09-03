---
title: "Publish an open-source installation guide"
status: closed
labels:
  - wayfinder:task
parent: null
assignee: null
blocks: []
blocked_by: []
---

## Problem Statement

开源使用者需要在不了解本仓库内部实现的前提下，在本机安装依赖、配置翻译模型、启动服务、生成中文阅读版 PDF，并在失败时定位配置问题。

## Solution

README 提供从系统依赖、克隆、环境变量、Chromium、Ollama、三进程启动、首个任务、产物说明到常见故障的可复制指南；所有陈述以当前本地优先双模型和重排实现为准。

## User Stories

1. As an open-source user, I want to know the supported operating systems and runtime versions, so that I can prepare a compatible machine.
2. As a first-time installer, I want copyable setup commands, so that I can start without reading source code.
3. As a local-model user, I want to configure Ollama separately from the remote reviewer, so that translation cost and quality are controlled.
4. As a privacy-conscious reader, I want to know which content can reach a remote provider, so that I can make an informed choice.
5. As a reviewer, I want to find the generated PDF and reports, so that I can inspect layout and download the result.
6. As an operator, I want health checks and troubleshooting steps, so that I can distinguish dependency, model, port, and font failures.
7. As a contributor, I want test commands, so that I can verify changes before submitting them.

## Implementation Decisions

- Make the README the user-facing installation source of truth and link deeper contracts rather than duplicating them.
- Document the supported `reflow` default and the legacy `overlay` comparison mode separately.
- Describe local Ollama plus optional OpenAI-compatible remote review as one coordinated workflow, including its degraded states.
- Use the existing development launcher as the primary start seam; preserve manual startup as a diagnostic alternative.

## Testing Decisions

- Validate every documented command against the existing Python, Playwright, FastAPI, Runner, and Next.js seams.
- Cover the observable startup outcome: API health endpoint, running Runner, browser UI, generated PDF, and format report.
- Keep test instructions aligned with the established full Python suite, web test, and production build commands.

## Out of Scope

- Hosted deployment, account management, provider credential vaults, OCR, and production performance claims.

## Further Notes

The local tracker does not define the skill-required `ready-for-agent` triage label; this closed implementation record uses the repository's supported `wayfinder:task` label.
