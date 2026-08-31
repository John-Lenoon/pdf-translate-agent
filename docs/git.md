# Git Workflow

## Commit approval

默认由项目负责人审阅工作区改动。Agent 不自动执行 `git add`、`git commit` 或远程推送。

只有在项目负责人明确同意后，Agent 才可以执行获授权的 Git 操作。授权范围按当前回复确定；“可以提交”仅代表允许本地 commit，不自动代表允许 push。

## Commit message format

提交信息使用 Conventional Commits：`<type>: <简短描述>`。

| Type | 使用场景 | 示例 |
| --- | --- | --- |
| `feat` | 新增功能、接口、页面或模块能力 | `feat: add segment translation endpoint` |
| `fix` | 修复错误、逻辑问题或边界情况 | `fix: preserve cross-page paragraphs` |
| `refactor` | 代码重构，功能行为不变 | `refactor: split workflow repository` |
| `style` | 格式、空格、换行或格式化调整，逻辑不变 | `style: format Python sources` |
| `test` | 新增或修改测试、补充测试覆盖 | `test: add AST segmentation cases` |
| `chore` | 工程杂项、依赖、配置、脚本或 `.gitignore` | `chore: pin uv dependencies` |
| `docs` | 仅文档变更 | `docs: define V1 acceptance criteria` |

描述使用祈使句、简短明确；一个 commit 尽量只包含一个逻辑变更。不要把密钥、原始 PDF、完整译文、本地 SQLite、`runs/` 产物或 `.env` 提交到仓库。

## Pre-commit checklist

1. 查看 `git status`，确认没有混入无关或敏感文件。
2. 运行与改动相关的测试和 `git diff --check`。
3. 若改动影响用户可见行为、启动方式、版本、环境变量、输入输出或版本范围，检查 `README.md` 是否已同步。
4. 检查 commit diff，确认只包含本次授权范围。
5. commit 后报告 commit hash、验证命令和未提交改动。

## Push policy

远程推送是独立的外部状态变更。即使已获准创建 commit，Agent 仍必须在执行 `git push` 前获得明确的 push 授权，并确认目标 remote 和 branch。
