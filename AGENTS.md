
# AGENTS.md — omnicompany 工作约定(短锚点, 非权威副本)

> 本文件只是**指针**, 不复制规则。权威各有其处, 这里只提醒"该想起来用什么"。
> 详细规范走 `docs/standards/`(`self_creative_content_three_files.md` / `concepts/plan.md` / 等)。

## 用公开内容前: 先查本地资产(高频盲区 → 在此锚定)

用户提到任何公开领域内容、说"参考 X 源码/项目"、或要调研某主题前, **先查本地, 别假设"没有"也别问用户"在哪拉的"**:

```
omni refs find "<关键词>"        # 研究记录 + 已拉 repo + 资料, 一把查; 有就有, 没有就没有
```

本地已拉 50+ 参考仓(`claude-code-analysis`=真 Claude Code 源码 / `codex` / `claudecodeui` / `agents/*` / `gemini-cli` …)+ 已调研的研究记录, 都进了统一 catalog。别名召回("claude code 源码"→`claude-code-analysis`)。catalog 真源 `data/domains/research/library/catalog.json` 可直接 grep; 新拉了 repo 或想刷新跑 `omni refs sync`。

> 这一条专治"用户说参考 X、agent 没注意到本地早有 X"。查了再动手。

## 治理与提交习惯(高频, 易忘 → 在此锚定)

omnicompany 把重复性治理收成"治理部门"管线, 一条命令即可发现:

```
omni governance catalog          # 看有哪些治理管线 + 档期 + 上次跑没跑
```

**收尾一段实质工作前, 过一眼 catalog**, 该跑的跑一下。常用:

- `omni governance commit-run`     性价比模型严格分批 git 提交(默认 dry-run 出计划, `--apply` 真提交)。
  **git 改动会越堆越难管 → 大改后或定时跑它**, 不要让工作区无限累积。
- `omni governance docs-refs`      文档断链体检(确定性, 不调模型)。
- `omni governance plans-run --only-missing`   新计划归属 + 中文标题。
- `omni governance docs-timeliness` / `history-run`  规范时效性 / 重复需求挖掘(性价比模型)。

## 两条治理原则(决定"怎么用")

1. **语义判断优先用性价比模型 agent, 规则是批量规律的结晶**
   (`docs/standards/concepts/governance_semantic_first.md`)。别用脆弱字符串规则做语义判断。
2. **提交不该由贵模型顺手做**, 交给 `commit-run`; 贵模型只在它判不准时兜底。

## 定时(把"想起来"从人身上卸下来)

可定时的治理已挂 `.omni/cron/`(由 OmniSentinel / cron 守护消费), 见
`docs/plans/omnicompany-governance/[2026-06-13]GOVERNANCE-PIPELINE-ECOSYSTEM/plan.md`。
schedulable 的根本不需要"想起来"; 只有交互式判断才需要人/agent 主动起意。
