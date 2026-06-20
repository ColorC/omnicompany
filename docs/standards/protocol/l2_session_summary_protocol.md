# L2 Session 总结协议 (compact / 新 team / 验证收尾 三时机)


> L1 2026-04-26 立. 适用对象: L2 (Claude Code / 任何 LLM agent) 在 omnicompany 项目里所有需要"显化决策" 的工作。

## 一、为什么要立这套规程

omnicompany 终极目标是**让机器无监督工作** — 三大子方向: **学习 / 自稳自控自扩张 / 全自动语义工作流**.

但 L2 跟 claude code 直接交互时, **决策显化不够**:
- 做了什么没列清单
- 数据是否落盘没确认
- 假设有没有写下来没人知道
- 验证基于什么假设没追溯
- 假设之间的依赖树没整理

不显化 → 后续 session / 其他 L2 / L1 自己都重头猜 → 重复成本高 → 跟 L1 立的"数据密集型开发, 决策显化"本意背离.

本协议补这个空白: **每个 trigger 时机 L2 必须按 checklist 总结**.

## 二、四个 trigger 时机

| Trigger | 描述 |
|---|---|
| **T1: compact 前** | session 上下文将被压缩前, 必走本协议 |
| **T2: 用户主动要求** | L1 显式要求做总结时 (例: "总结一下 / 整理一下") |
| **T3: 新 team 开启** | 准备开新 team / pipeline / service 立项时, 写本协议作起点档 |
| **T4: 验证完成 + 收尾 team** | 一个 team / pipeline / service 验证通过 + 准备收工时 |

L2 默认在每次 session 后期主动检查上述 trigger, 满足任一即触发本协议.

## 三、总结文件位置 (按职责拆分)

### 整体进度: `docs/plans/<主题>/[YYYY-MM-DD]<sub-plan>/`

- 主题目录按 omnicompany 8 大簇分: `voxel_engine / visual-pipeline / new-services / core-architecture / agent-routerization / arch-debt-and-naming / hypothesis-system / meta-self-publishing`
- 每个具体 plan 是日期前缀的子目录 (例 `[2026-04-25]REPORT-AUTHOR-TEAMS`)
- 子目录里含: `plan.md` (常规计划) + `compact_summary_<YYYY-MM-DD>.md` (本协议产出, 多次 compact 多个文件)

放在这里的内容:
- 本次推进了什么
- 大概的反馈
- 重要教训
- 下一步即将做什么
- 引用了什么参考资料

### 假设 / 实验数据 / 结论: 各管线的"健康文档" (按分布式文档策略)

- 位置: `src/omnicompany/packages/services/<service>/DESIGN.md` 七节里的对应节 (按 `docs/standards/_global/distributed-docs.md` 规范)
- 内容: 客观全面罗列性质 — 假设原文 / 实验数据原文 / 结论
- 任何 worker / team / pipeline 的健康文档必须含: 假设清单 / 验证情况 / 数据落盘位置

**计划要更新, 健康档案也要更新. 缺一个等于决策没显化.**

## 四、总结内容 checklist (硬性, 缺项即不算完成)

每次 trigger, L2 必须在总结里列以下 8 项. 缺一项必须显式标 "未做 (理由 X)" 而不是省略.

### 4.1 常规三项 (本协议之前已习惯做的)

- [ ] **本次推进的进度** (做了什么 + 阶段性结果)
- [ ] **下一步即将做的事情**
- [ ] **参考资料** (commit / plan / wiki / 外部链接)

### 4.2 代码范畴 (须列, 不可概括跳过)

- [ ] **本次完成的代码范畴**: 可概括 (例: "改了 3 个 service 的 prompt"), **但**:
  - **如果做了 team / worker, 必须每个列出** (含 service path + worker class 名 + 简短一句"做什么")
  - 如果做了纯脚本 / 工具, 列出脚本路径

### 4.3 实验情况 (运行结果 + 数据落盘 + 可搜索)

- [ ] **本次生成的 worker / team 的实验情况**:
  - 运行日志在哪里? (具体路径)
  - 数据库 (events.db / sqlite bus / etc) 里**是否有**?
  - 如果有, **如何搜索到** (用什么搜索方式 + 实际搜索证明 — 即在 summary 里粘 grep / sqlite query 命令 + 输出片段)
  - 实验结果如何 (PASS / FAIL / 无结果)
  - **如果没有数据**: 下一步必须**立刻**把所有内容接入事件总线. **一切有意义产物必须留痕**. 不留痕 = 没做.

### 4.4 工作性假设 (每个 worker / team 至少 1 个)

- [ ] **本次提出的工作性假设**:
  - 每个 worker 至少对应 1 个假设, 形如: "假设 [X 内容] 可以在 [Y 情况] 下工作"
  - 每个 team 至少对应 1 个假设, 形如: "假设 [X 内容] 可以通过 [Y SOP / 工作流 / 处理方式] 在 [Z 信息空间] 内处理好"
  - 假设要写在哪里? 优先放该 worker / team 的 DESIGN.md 七节 + 在 compact_summary 里复述

### 4.5 验证 + 验证性假设 (每个关键产物 + 每个程序测试)

- [ ] **关键产物的验证情况**:
  - 列出本次 worker / team 的关键产物
  - 每个产物 — 每次产出是否有验证 (PASS/FAIL/无验证)
  - 没验证的: 显式记录 (优先级低于数据库, 但出问题时必补阶段性验证)
- [ ] **验证背后的假设**:
  - 每个验证 (含每个程序测试 — 即使不在管线中, 只要本次写的"测试"都要记) 背后都有必要性假设
  - 形如: "如果 [X 要验证的] 健康, 那 [Y 方面] 应当表现为 [Z]"

### 4.6 假设树 (依赖关系)

- [ ] **整理假设成树**:
  - 4.4 + 4.5 列出的假设之间有没有依赖? (一个假设的成立依赖另一个假设)
  - 有依赖的统一放一起, 明确依赖箭头
  - 思考有没有**共同假设**和**依赖链** (多个假设共享同一个底层假设)

### 4.7 假设验证情况 (compact 前必整理完)

- [ ] 每个假设的验证状态:
  - **完全证明** (本次实验数据 / 网络已知 / 用户确认 等支持)
  - **部分证明** (有支持但有边界条件 / 不全)
  - **完全证否** (实验数据反驳 / 用户否定)
  - **未确认** (没数据)
- [ ] 来源标注:
  - 哪些是**用户确认**的 (引用对话原话或 memory 文件)
  - 哪些是**网络搜索可证** (引用 URL + 摘要, 类似 v7 web_fetch 用法)
  - 哪些是**本地其他地方可搜索** (引用文件路径 / commit / DESIGN 节)
  - 哪些**还没确认** (本次的待办)

### 4.8 总览句 (一句话答 5 个核心问题)

- [ ] 一句话总览 (不超过 200 字), 必须涵盖:
  1. 做了什么
  2. 运行了什么
  3. 运行结果如何
  4. 如何证明做好了
  5. 这一切合理的依据 / 理论是什么

## 五、与 PROGRESS.md / DESIGN.md / 控制结构.md 的关系

| 文档 | 角色 | 频率 |
|---|---|---|
| `docs/PROGRESS.md` | 全局状态权威 (最新 5-8 条) | 每个 trigger 后**回更**最新条 |
| `src/omnicompany/packages/services/<X>/DESIGN.md` | 该服务的健康档案 (含假设清单) | 每个 trigger 后**回更**对应节 |
| `docs/plans/<主题>/[date]<plan>/compact_summary_*.md` | 本协议产出 (本次 trigger 完整 checklist) | 每个 trigger 一份新文件 |
| `docs/控制结构.md` | 规则权威 (本协议被它引用) | 立时引用一次, 后续不动 |

冲突解法: 跟 `控制结构.md` 冲突, 以 `控制结构.md` 为准 + 同步本协议.

## 六、自动化 (hook / skill)

短期 (本协议立的当下): L2 自觉. 在每次 compact 前 / 用户提"总结 / 整理" 时主动 follow.

中期: 加 hook (claude code settings.json 里 `Stop` hook), 在 session 即将结束前自动提示 L2 走本协议.

长期: 立 skill `compact-summary-l2` 给 L2 调用, 自动产 checklist 模板。

## 七、违反本协议的后果 (L2 自我约束)

任一 trigger 后, **总结文件不存在 / checklist 缺项 / 数据没落盘 / 假设没列**, 都视为 **决策没显化** = 跟 omnicompany 终极目标背离.

补救: 立刻补 checklist 的缺项, 该接事件总线就接, 该补 grep / sqlite 证明就补. 不允许跳过 + 默认 OK。

## 八、版本

- v1 (2026-04-26): L1 立, L2 (Claude Code) 起草. 触发场景: omnicompany 三档发布管线 + 文章自动写作 (report_author / publish_pipeline) 反复跑出 7 版差异, L1 反复纠偏揭示 "项目级目标管理 + L2 决策显化" 的根本缺口.

## 九、参考

- `docs/控制结构.md` (规则权威 + 五层角色)
- `docs/PROGRESS.md` (状态权威)
- `docs/standards/_global/distributed-docs.md` (分布式文档策略)
- `docs/standards/_global/llm_first.md` (LLM 优先铁律)
- memory `feedback_humble_publishing_no_exaggeration.md` (谦逊发布铁律)
- memory `feedback_design_is_antidrift_not_review.md` (DESIGN 自防漂移本意)
