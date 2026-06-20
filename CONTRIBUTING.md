
# Contributing to omnicompany

本指南面向人类贡献者和 AI agent。它只做入口索引和最低协作约束；规则权威仍以 [docs/控制结构.md](docs/控制结构.md)、[docs/standards/](docs/standards/) 和 [AGENTS.md](AGENTS.md) 为准。

## Before You Start

- 先读 [README Quick Start](README.md#快速开始--quick-start)，按仓库根目录安装本地开发环境。
- 如果任务涉及公开项目、源码参考或主题调研，先运行 `omni refs find "<关键词>"`，确认本地 catalog 里是否已有研究记录或已拉取仓库。
- 如果任务涉及 omnicompany 的角色分工、派发边界或正式报告格式，以 [docs/控制结构.md](docs/控制结构.md) 为唯一规则权威。

## Development Setup

```bash
git clone <repo-url> omnicompany
cd omnicompany
pip install -e .
```

更多安装方式见 [README.md](README.md)。LLM 相关命令需要仓根 `.env` 配置；不要提交真实密钥，使用 [.env.example](.env.example) 作为模板。

## Tests

提交前优先运行默认快速测试：

```bash
pytest -m "not e2e and not slow"
```

`e2e` 和 `slow` 标记的测试可能需要真实 API key、外部服务或较长运行时间。只在任务明确需要时运行，并在 PR 说明里写清楚前置条件与结果。

## Project Conventions

- 文件、模块、服务应带 OmniMark 头；格式权威见 [docs/standards/cli/omni-header.md](docs/standards/cli/omni-header.md)。
- 代码层目录结构以 [src/omnicompany/README.md](src/omnicompany/README.md) 和 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) 为导航。
- README / DESIGN / SKILL 三件套和文档分布规范见 [docs/standards/protocol/self_creative_content_three_files.md](docs/standards/protocol/self_creative_content_three_files.md)。
- 计划目录、命名和归档约束见 [docs/standards/concepts/plan.md](docs/standards/concepts/plan.md)。

## Commit Guidance

- 使用 Conventional Commits，例如 `feat: ...`、`fix: ...`、`docs: ...`、`test: ...`、`chore: ...`。
- 一段实质工作收尾前，先查看治理管线：

```bash
omni governance catalog
```

- 大改或准备提交时，优先用治理部门规划提交：

```bash
omni governance commit-run
```

确认计划后再按需要使用 `omni governance commit-run --apply`。提交拆分应服务于可审查性：每个提交只表达一个清晰意图。

## Pull Request Workflow

PR 应包含：

- 变更目的和范围。
- 关键文件或模块入口。
- 已运行的验证命令和结果。
- 未运行测试的原因。
- 对安全、配置、数据迁移或外部服务的影响说明。

AI agent 提交或协作时，还应说明是否在替 L3/L4/L5 顶班、是否绕过了管线，以及依据哪个本地权威文档做判断。不要把 [docs/控制结构.md](docs/控制结构.md) 或其他标准整段复制进 PR；引用链接即可。

