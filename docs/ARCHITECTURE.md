# OmniCompany Architecture

> **This document is the human-readable description.** 从 Session 3a (2026-04-08) 起，
> **机器可读的权威源**是 [`docs/archmap.yaml`](archmap.yaml) —— OmniGuardian (OMNI-014 /
> OMNI-015 / 未来的 guarded_write 门禁) 全部从那里读取 drawer 定义。
>
> 两份文档的职责分工：
> - `archmap.yaml` — 唯一权威，结构化 YAML，人 + 机器都能用。修改需 human 审阅批准。
> - `ARCHITECTURE.md` (本文件) — 人类友好的说明文字，解释设计理由和依赖契约。
>
> **如果两份文档冲突以 archmap.yaml 为准**，请同时更新两份。
>
> 常用命令:
> - `omni guardian archmap show`     查看结构树
> - `omni guardian archmap validate`  校验 YAML 格式
> - `omni guardian archmap check <path> --writer <identity>`  试判一个路径
>
> Last structural migration: 2026-04-07 (see `docs/plans/[2026-04-07]TARGET-ARCH/`)

## The ten drawers

```
src/omnicompany/
├── core/           ★ Framework glue (config, registry, dispatch, pipelines, observe, omnimark, omni_shield)
├── bus/            ★ Event bus (SQLite, Memory)
├── protocol/       ★ Wire types & interface contracts
├── primitives/     ★ Abstract interfaces (Hook, Intent, Node, Signal, Tool) — zero impls
├── runtime/        ★ Pipeline execution + Agent loops (+ runtime/nodes/)
├── tracing/        ★ IntentTracer
├── cli/            ■ CLI interface
├── dashboard/      ■ Web UI (FastAPI + Vite)
├── packages/       ● Domain implementations (flat, one subdir per domain)
└── _graveyard/     × Retired code (NEVER imported by live code)
```

## What goes where

| Drawer | What belongs here | What doesn't |
|---|---|---|
| **`core/`** | Pipeline registry, dispatch, config, observe SDK, OmniMark file identity, OmniShield write permit. Framework glue loaded by every caller. | Business logic. LLM-specific code. Agent loops. |
| **`bus/`** | `SQLiteBus`, `MemoryBus`, `EventBus` base class. Event transport primitives. | Anything that interprets event payloads. |
| **`protocol/`** | `Format`, `Router`, `PipelineSpec`, `FactoryEvent`, `Anchor`. Stable wire layer — rarely changes. | Any code that *consumes* these types (that lives in `runtime/` or `packages/`). |
| **`primitives/`** | **Abstract** `Hook`, `Intent`, `Node`, `Signal`, `Tool` interfaces. Contracts only, no implementations. | Any concrete Router or Node impl — those go in `packages/<domain>/`. |
| **`runtime/`** | `PipelineRunner`, `LLMClient`, `ToolExecutor`, agent loops (`agent_node_loop`, `ide_agent_loop`), DAG builder, session management, routing. | Domain-specific logic. UI code. |
| **`tracing/`** | `IntentTracer` and trace data schema. | Event bus wiring (that's `bus/`). |
| **`cli/`** | Click commands. Thin wrappers over `core.dispatch` / `core.observe`. | Business logic. Agent state. |
| **`dashboard/`** | FastAPI backend + Vite frontend. Thin wrappers over `core.observe` + SSE. | Any business logic or agent state. |
| **`packages/<domain>/`** | One domain of business code. Self-contained: `formats.py`, `routers/`, `pipeline.py`, `run.py`. | Cross-package imports to another `packages/<other>/`. Use `primitives/` interfaces for inter-domain interaction. |
| **`_graveyard/`** | Retired code that may be revived. **Not a package**, just an archive path. | Anything imported by live code. |

## Dependency contracts

Who may depend on whom. Violating these creates structural drift and will be
caught by OmniGuardian post-Phase E.

```
  protocol  ←  bus      primitives
      ↑        ↑             ↑
      └────────┴─────────────┤
                             │
                            core
                             ↑
                         runtime
                             ↑
                      ┌──────┴──────┐
                      │             │
                 packages        tracing
                      ↑             ↑
                      └─────┬───────┘
                            │
                    ┌───────┴───────┐
                    │               │
                   cli          dashboard
```

Rules:
- `protocol/`, `bus/`, `primitives/` never import from anything below them in the diagram
- `core/` imports `protocol/`, `bus/`, `primitives/` — never `runtime/` or above
- `runtime/` imports `core/` and lower — never `cli/`, `dashboard/`, or `packages/`
- `packages/<domain>/` imports everything below but **never another `packages/<other>/`**
- `cli/` and `dashboard/` are parallel — they don't import each other

## The `packages/` subpackage list

After the 2026-04-07 migration, `packages/` is completely flat. Each subdir is
an independent domain with `formats.py` + `routers/` + `pipeline.py` + `run.py`
at minimum:

| Package | Purpose | Dispatchable as |
|---|---|---|
| `packages/domains/gameplay_system/` | Game config learning + production + Unity QA (absorbs former `primitives_impl/gameplay_system/` as `table_learning/` subfeature) | `omni run gameplay_system-learn` / `gameplay_system-produce` / `unity-*` |
| `packages/domains/voxel_engine/` | voxel_engine voxel game domain (design, engineering, art, PM, QA; includes `mechanics_evolver/` subfeature) | `omni run voxel_engine.*` |
| `packages/domains/software_engineering/` | Software engineering agents (plan, design, TDD, implement, review, verify; includes `generated/` subfeature) | `omni run sw-*` |
| `packages/domains/creative_content/` | creative_content creation engine (experimental) | — |
| `packages/services/guardian/` | **OmniGuardian** architectural immune system. Auto-started by `runtime/runner.py:_ensure_guardian_running()` on every PipelineRunner boot. | `omni guardian patrol` / `omni run guardian` |
| `packages/services/evolution/` | Evolution workflow (orchestrator, hypothesis board, experiment runner, replay runner, diagnosis) | — |
| `packages/services/trace_induction/` | Convert execution traces into reusable patterns | `omni run trace-induction` |
| `packages/services/pattern_discovery/` | Discover structural patterns in historical data | `omni run pattern-discovery` |
| `packages/services/lap_auditor/` | LAP (Language Anchoring Protocol) compliance auditor | `omni run lap-audit` |
| `packages/services/cleanup_bot/` | Automated cleanup pipeline | `omni run cleanup` |
| `packages/services/pipeline_ci/` | CI for pipeline definitions | `omni run pipeline-ci` |
| `packages/services/selftest/` | Self-diagnostic pipeline | `omni run selftest` |
| `packages/services/skill_importer/` | Import external Claude Skills into OmniCompany | `omni run skill-import` |
| `packages/services/workflow_factory/` | LLM-driven workflow generation | `omni run workflow-factory` |
| `packages/vendors/mcp_builder/` | MCP server scaffold generator | — |

## Immune systems

Two subsystems exist to catch structural drift before it accumulates:

**OmniGuardian** (`packages/services/guardian/`) — post-facto scanner, active
- Rules in `packages/services/guardian/patrol.py`: OMNI-001 through OMNI-007 today,
  OMNI-008+ added post-Phase E to codify the new drawer labels
- Runs as a background daemon auto-started by every `PipelineRunner`
- Dispositions: warn → stamp → quarantine → tow truck

**OmniShield** (`core/omni_shield.py`) — write-time interceptor, audit-only
- `ALLOWED_WRITE_ROOTS` whitelist + `FORBIDDEN_WRITE_PATHS` blacklist
- Currently logs but does not block (`audit_only=True`)
- Phase E will add `src/omnicompany/` root-level writes to the forbidden list
  and wire Shield into the agent tool layer

## What's NOT here (intentionally)

These are frequently-asked questions about where things live:

- **Event databases** — still fragmented across `data/*/events.db` etc.
  A future "Move 8" will unify into a single `data/events.db` with a
  `domain` column. See `docs/plans/[2026-04-07]ARCH-TIDY/tidy_proposal.md`
  Move 8.
- **Skills** (Claude skills) — live at `.claude/skills/` at repo root, not
  under `src/omnicompany/`. They're loaded by the Claude Code runtime, not
  by omnicompany itself.
- **Tests** — live at `tests/` at repo root. Mirrors `src/omnicompany/`
  structure loosely.
- **Pipeline registrations** — declared in `core/pipelines.py` via
  `_lazy_fn()` strings. This is the central registry; lazy loading means the
  domain packages aren't imported until `omni run <name>` is called.
  **Guardian is the exception**: it's imported eagerly by `runtime/runner.py`
  to start the patrol daemon.

## History

- **2026-03-24**: initial architectural diagnosis
  (`docs/plans/[2026-03-24]ARCH-DIAGNOSIS-AND-CLEANUP/diagnosis.md`)
- **2026-04-07**: full structural migration executed
  (`docs/plans/[2026-04-07]TARGET-ARCH/`). 14 commits from `e22e41a` (baseline)
  to `8dca4dc` (`packages/omnicompany/` wrapper delete). Phases A, B.1-B.10,
  B', C.
- Pending: Phase D (runtime/ subdir split) + Phase E (Guardian rule additions,
  OmniShield enforce mode)

## For agents working in this codebase

If you're an agent editing this codebase, read this doc first before adding
a new file. If you don't know which drawer your file belongs in, it probably
needs to be a new subdir under `packages/<your_domain>/`, not a root-level
file and not a new top-level dir.

Never:
- Create `.py` files directly under `src/omnicompany/` (only dunder files
  allowed at root)
- Import from `_graveyard/`
- Use `primitives_impl`, `packages.omnicompany`, or `packages.imported`
  in any import path or string literal (these drawers no longer exist)
- Create new top-level directories without updating this doc and Guardian
