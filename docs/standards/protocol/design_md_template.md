<!-- [OMNI] origin=claude-code domain=standards ts=2026-04-17T00:00:00Z type=doc status=active -->
<!-- [OMNI] material_id="material:standards.protocol.design_md_structure_template.md" -->

# DESIGN.md 标准模板与检测规范

> **权威来源**：`self_narrative_three_files.md`（自我叙事三件套规范，2026-05-04 立）——本文件是其 DESIGN.md 模板**细则**，冲突时以三件套规范为准
> **2026-06-13 切换**（用户裁决"规范冲突以新的为准"）：「核心目的」段移交 README 承载，DESIGN 必需节从七节改六节；Guardian OMNI-034c 已同步
> **相关规范**：`distributed-docs.md`（位置规范）、`omni-header.md`（OmniMark 头）
> **Guardian 规则**：OMNI-034（结构检测）

---

## 一、为什么要固定结构

两条理由：

1. **agent 和人都能按固定章节快速导航**——"找架构决策？直接跳第三节。" 自由结构 = 每份文档都要重新理解。
2. **系统可检测未完成**——只有固定结构才能用规则引擎扫出"哪些节没填"。

偏离本模板的 DESIGN.md 会被 Guardian OMNI-034 告警。

---

## 二、标准模板（复制这份）

```markdown
<!-- [OMNI] origin=<origin> domain=<domain> ts=<ISO8601> type=doc status=<skeleton|design|active|deprecated> -->

# <模块名> · 设计文档

## 状态
- **版本**: V<n>
- **成熟度**: skeleton | design | active | deprecated
- **下一步**: <1 行简述当前最紧迫的下一步>

<!-- 「核心目的」(为什么存在) 写在同目录 README.md，不写进 DESIGN（三件套规范 §五） -->

## 核心接口
<!-- 对外暴露的关键类/函数/协议。列表形式，含源码链接 -->
<!-- 例: - `PipelineRunner.run(initial_input)` — runner.py:1174 -->

## 架构决策
### D1 — <决策标题（≤ 20 字）>
<为什么这样做、考虑过什么替代方案、取舍是什么>

### D2 — <决策标题>
...

## 数据流 / 拓扑
<!-- 输入→处理→输出。或关键组件协作图（ASCII art 可接受） -->

## 已知局限
1. **<局限标题>** — <现状 + 未来升级路径>
2. ...

## 参考资料
- <源码路径 / 外部链接 / 关联 plans>

## 内部构成
<!-- 可选节，仅有子模块时写。指针式列表，指向各子模块自己的 DESIGN.md，不复述其内容 -->

## 接收意愿
<!-- 可选节，仅基础设施模块需写。详见 §九。 -->
```

---

## 三、硬性要求（Guardian 强制）

### 3.1 OmniMark 头

**必须**是第 1 行，格式严格：

```
<!-- [OMNI] origin=... domain=... ts=... type=doc status=... -->
```

字段：
- `origin`：`claude-code` / `claude-l3` / `human`（写这份文档的来源）
- `domain`：模块标识（如 `runtime/exec`、`services/absorption`）
- `ts`：ISO 8601 时间戳（最近一次实质性更新）
- `type`：**必须** `doc`
- `status`：**必须** 四选一：
  - `skeleton`：骨架，多数节未填（见 §五）
  - `design`：设计中，已实现部分但仍在迭代
  - `active`：对应代码稳定运行，文档反映现状
  - `deprecated`：模块已废弃或被替代

### 3.2 六个二级标题

**必须齐全**（文字固定，不可改名、不可省略）：

1. `## 状态`
2. `## 核心接口`
3. `## 架构决策`
4. `## 数据流 / 拓扑`
5. `## 已知局限`
6. `## 参考资料`

缺任何一个 Guardian 告警（OMNI-034c）。

可选节（按需添加，不告警）：`## 内部构成`（有子模块时，指针式）、`## 接收意愿`（基础设施模块，见 §九）。
「核心目的」属于 README（三件套规范 §五）；存量 DESIGN.md 中残留的 `## 核心目的` 不算违规，下次实质性更新时迁去 README。

### 3.3 架构决策至少 1 条（design / active 状态）

`skeleton` 状态下 `## 架构决策` 可全 TBD；`design` / `active` 状态下必须至少有一个 `### D1 — ...`。

### 3.4 `active` 状态不允许任何 TBD

`status=active` 的文档里若出现 `TBD`、`待补充`、`<!-- TBD:` 等标记，Guardian 报 **HIGH 级** 告警。
原因：active 意味着"文档反映代码现状"，不应该有未填的坑。

---

## 四、Status 生命周期

```
新建 → skeleton → design → active ⇄ deprecated
                    ↑           ↓
                    └── 发现严重偏差时回退 ──┘
```

### skeleton
- 文档骨架已建（7 节都在），内容以 TBD 占位
- 可被 Guardian 统计为"未完成"，dashboard 可见
- 适用：新包刚建、批量初始化时

### design
- 至少填了 `核心目的` + `核心接口` + 1 条架构决策
- 代码可能还在迭代，文档也在同步迭代
- 适用：功能开发中

### active
- 对应代码稳定运行，文档反映现状
- 所有节填满，无 TBD
- 适用：生产环境使用的模块

### deprecated
- 模块已废弃或被替代
- 文档保留供历史追溯
- `## 已知局限` 首项说明"被 X 替代，见 Y"

---

## 五、TBD 标记规范

### 5.1 整节未填

```markdown
## 核心接口
<!-- TBD: 此节尚未填充 -->
```

HTML 注释，渲染不可见，但 Guardian 能扫到。**只允许在 `status=skeleton`/`design` 时使用**。

### 5.2 部分未定

```markdown
## 架构决策
### D1 — 同步 vs 异步设计
<理由和取舍>

### D2 — 重试策略
_待补充：需要跟 OP 确认 SLA 要求_
```

斜体标记，渲染可见提醒人。Guardian 扫到后列为"部分待定"。

### 5.3 骨架模板（可直接复制）

```markdown
<!-- [OMNI] origin=claude-code domain=<DOMAIN> ts=<TS> type=doc status=skeleton -->

# <MODULE> · 设计文档

## 状态
- **版本**: V0 (skeleton)
- **成熟度**: skeleton
- **下一步**: 填充核心目的与接口

## 核心目的
<!-- TBD: 此节尚未填充 -->

## 核心接口
<!-- TBD: 此节尚未填充 -->

## 架构决策
<!-- TBD: 此节尚未填充 -->

## 数据流 / 拓扑
<!-- TBD: 此节尚未填充 -->

## 已知局限
<!-- TBD: 此节尚未填充 -->

## 参考资料
<!-- TBD: 此节尚未填充 -->
```

---

## 六、OMNI-034 Guardian 规则

### 检查对象

Guardian 扫以下位置的所有 `DESIGN.md`：

- `src/omnicompany/packages/**/DESIGN.md`
- `src/omnicompany/runtime/**/DESIGN.md`
- `src/omnicompany/protocol/DESIGN.md`
- `src/omnicompany/core/DESIGN.md`
- `src/omnicompany/bus/DESIGN.md`

### 检查项

| # | 项 | Severity | 说明 |
|---|---|---|---|
| 1 | OmniMark 头缺失或格式错 | HIGH | 必备元信息 |
| 2 | `status` 字段不在四选一 | HIGH | 枚举约束 |
| 3 | 七个二级标题不齐全 | HIGH | 结构硬约束 |
| 4 | `status=active` 含 `TBD`/`待补充` | HIGH | active 不应有坑 |
| 5 | `status=design`/`active` 但 `架构决策` 全空 | MEDIUM | 至少 1 条 |
| 6 | `status=skeleton` 列出缺失节 | INFO | 统计用，不阻塞 |
| 7 | `ts` 超过 90 天未更新（且状态非 deprecated）| LOW | 可能过时 |

### 期望的 Guardian 输出

```
[OMNI-034] DESIGN.md 结构检查:
  ✓ active:   9 个（完整反映现状）
  ⚠ design:   3 个（正在迭代）
  ◌ skeleton: 42 个（骨架占位，待填充）
  ✗ missing:  6 个模块完全没有 DESIGN.md
  ❗ stale:    2 个（> 90 天未更新但非 deprecated）
```

---

## 七、`.omni/manifest.yaml` 与 `DESIGN.md` 关系

`.omni/manifest.yaml` 是**机器可读**元数据（包清单、管线 ID、status）。
`DESIGN.md` 是**人+agent 可读**详述（为什么这样设计、有哪些决策）。

两者互补，都要有。manifest 被 Doctor / registry 消费，DESIGN 被 agent / 人审阅消费。

manifest 里 `plan_doc` 字段指向 DESIGN.md：

```yaml
pipelines:
  - id: absorption.v3
    status: active
    plan_doc: DESIGN.md
```

---

## 八、agent 如何使用这份规范

当 agent（如 SelfResearchLoop 或 dispute loop）需要了解 OmniCompany 某个模块时：

1. 从 `src/omnicompany/README.md` 顺链到该模块目录
2. 读该目录的 `DESIGN.md`：
   - 跳 `## 状态` 看 `status`（skeleton 则回到源码，active 则信任文档）
   - 跳 `## 核心目的` / `## 核心接口` / `## 架构决策` 获取语义
3. 读 `## 参考资料` 顺链到源码做二次验证

这符合项目两大铁律：
- **不截断**：agent 按需顺链读取，不预加载
- **信息空间完整可达**：每个模块都能顺链找到，没有盲区

---

## 九、接收意愿（可选第 8 节，基础设施模块建议填）

### 9.1 为什么要有这档

wiki 的前 7 节描述"**我是什么 + 我做什么**"（能力清单 / 缺口 / 架构决策）。
但真正高价值的吸纳往往在"**还没意识到的维度**"——没见过 `smart_model_routing` 就不知道它是一个概念。

→ 接收意愿回答第三个问题：**"我欢迎吸收什么主题的进步（哪怕具体形式未知）？"**

absorption 管线的 ModuleExplorer 消费此档，能主动对比外部仓库与自家模块，
识别出超出已有 self_portrait / gap_registry 范围的潜在吸纳价值。

### 9.2 适用范围

- **建议填**：基础设施模块（`runtime/*`、`protocol/`、`core/`、`bus/`、`primitives/`、`tools/`、`tracing/`）
- **可不填**：domain 层模块（`packages/domains/*`）/ 纯 skeleton 文档
- Guardian OMNI-034g **INFO 级告警**（不阻塞），仅对基础设施模块在 active/design 状态下缺节时提醒

### 9.3 四字段规范

```markdown
## 接收意愿

- **welcome_themes**: 欢迎吸收的主题（自由文本，≥ 3 条）
  - <主题 1>
  - <主题 2>
  - <主题 3>
- **hard_constraints**: 硬约束，违反即不吸纳
  - <约束 1>
  - <约束 2>
- **soft_preferences**: 软偏好，违反降低优先级
  - <偏好 1>
- **maturity_preference**: `any` | `stable_only` | `production_validated`
```

字段语义：
- `welcome_themes` — 本模块欢迎吸收的进步主题（即使具体形式未知）。写法偏**领域/概念**，不偏"某个具体 API"
- `hard_constraints` — 违反即不吸纳（如 `runtime/llm` 的"单模型铁律 A 不可破"）
- `soft_preferences` — 违反降低优先级但不阻塞（如"偏好 qwen3.6-plus 兼容"）
- `maturity_preference` — 对外部源代码成熟度的要求：
  - `any` — 变化快的领域（LLM 调用层），新理论也可吸纳
  - `stable_only` — 需要稳定版/已发布
  - `production_validated` — 只吸纳生产环境验证过的模式

### 9.4 样例（`runtime/llm/`）

```markdown
## 接收意愿

- **welcome_themes**:
  - 多模型 ensemble / mixture of agents
  - 智能模型路由（按任务复杂度动态选型）
  - prompt caching 策略
  - 流式输出优化（背压 / token-level stop）
  - 成本归因与分摊
  - 新的 LLM provider API 接入范式
- **hard_constraints**:
  - 单模型铁律 A（qwen3.6-plus 为默认主模型；升级需 L2 许可）
  - 必须走统一聚合 API（不绕 LLMClient 直接调原生 SDK）
  - 成本敏感（默认不拉高 baseline token 预算）
- **soft_preferences**:
  - 偏好 qwen3.6-plus 兼容的协议/格式
  - 偏好异步 API 而非同步阻塞
- **maturity_preference**: any
```

---

## 十、Team 专属要求（新建 Team 必读）

> **适用**: 新建 Team 包（`src/omnicompany/packages/services/<team>/` 或 `packages/domains/<area>/<team>/`）
> **权威范本**: `packages/services/omnicompany/DESIGN.md`
> **命名**: Worker / Material / Team 是 2026-04-19 起新代码强制用的名字（见 `terminology.md`）

### 10.1 目录结构（硬规则）

```
<team>/
├── __init__.py          # re-export 主 API + 兼容 shim
├── DESIGN.md            # 本规范七节 + 可选第 8 节接收意愿
├── .omni/manifest.yaml  # 机器可读清单（见 §七）
├── formats.py           # Material 定义（F-19 kind 必填）
├── workers/             # Worker 子类集合
│   ├── __init__.py      # ALL_WORKERS 清单
│   ├── <worker_1>.py
│   └── <worker_2>.py
├── run.py               # 可选: 提供 run_<team>(job_spec) 入口
└── _archive/            # 老文件归档（类 A 迁移时）
    └── README.md        # 归档清单 + 原因 + 新位置
```

### 10.2 Material 定义（F-19 kind 必填）

`formats.py` 中**每个** Material 必须通过 `tags` 声明 `kind.source / kind.internal / kind.sink` 之一：

```python
from omnicompany.packages.services.omnicompany import Material  # Material = Format alias

MY_SOURCE = Material(
    id="<team>.<material>.request",
    name="...",
    description="...",         # F-01 五要素 + F-02 ≥ 100 字
    parent="requirement",
    tags=["<team>", "kind.source"],     # ← F-19 必含 kind.*
    json_schema={...},
    examples=[...],            # F-07 ≥ 1 合法样例
)

MY_INTERNAL = Material(
    id="<team>.<intermediate>",
    tags=["<team>", "kind.internal"],
    ...,
)

MY_SINK = Material(
    id="<team>.<output>",
    tags=["<team>", "kind.sink"],
    ...,
)

ALL_MATERIALS = [MY_SOURCE, MY_INTERNAL, MY_SINK]
```

**kind 速查**（见 `material.md` F-16 / F-19）：
- `kind.source` — 外部输入，无 producer 合法（`user_request`、`external_event`）
- `kind.internal` — worker 间流转，必须有 producer + consumer
- `kind.sink` — 最终输出，无 consumer 合法（`stdout`、`audit_log.entry`、`workspace_file_stock.persisted`）

### 10.3 Worker 定义（继承 omnicompany Worker）

```python
# workers/my_worker.py
from omnicompany.packages.services.omnicompany import Worker
from omnicompany.protocol.anchor import Verdict, VerdictKind

class MyWorker(Worker):
    """职责单一, 完整 FORMAT 边界, 独立测试价值 (R-18 粒度)."""

    DESCRIPTION = "..."                           # R-01 ≥ 20 字符
    FORMAT_IN = "<team>.<material>.request"      # 或 list[str] + FORMAT_IN_MODE
    # FORMAT_IN_MODE = "and" | "or"              # R-24 · list[str] 时必填
    FORMAT_OUT = "<team>.<output>"               # 单 str（Protocol 契约）

    def run(self, input_data: dict) -> Verdict:
        req = input_data.get("<team>.<material>.request", {})
        result = do_work(req)
        return Verdict(
            kind=VerdictKind.PASS,
            output={"field1": ..., "field2": ...},   # 平铺 (R-23), 非嵌套
            # 可选: output["_emit_as_new_job"] = True → 子 job (R-25)
        )
```

**Worker 粒度硬规则**（`terminology.md` §6.5）：
- 完整职责 + FORMAT 边界 + 独立测试价值
- **不是"每个函数一个 Worker"** — Worker 内部可保留纯函数库（如 guardian 的 `checks.py` 14 条规则函数被 `RuleEngineWorker` 调用）
- 反模式: 14 条 rule 拆 14 个 Worker → 样板爆炸 + O(F×R) 激活

**workers/__init__.py 清单**：

```python
from .my_worker_1 import MyWorker1
from .my_worker_2 import MyWorker2

ALL_WORKERS = [MyWorker1, MyWorker2]
__all__ = ["MyWorker1", "MyWorker2", "ALL_WORKERS"]
```

### 10.4 DESIGN.md 填写要求（在七节基础上）

对 Team 的 DESIGN.md，**核心接口** 节需列出 Worker 清单 + 入口函数；**架构决策** 至少 3 条（含 Worker 粒度 / Material kind / 预算等）；**数据流 / 拓扑** 画 Worker 订阅图（ASCII art 形式，标注 material kind）。

### 10.5 验证：过 MaterialDispatcher 跑 smoke

新 Team 落地验证（`material_dispatcher.py`）：

- 每 `(job_id, worker_id)` 激活一次（Q1 铁律）
- `orphan_workers()` 空（或所有 orphan 订阅 `kind.source`）
- `unconsumed_materials()` 空（或剩下的都是 `kind.sink`）

### 10.6 金标范本

- `packages/services/guardian/workers/` — 类 A 迁移 4 Worker（GitDiffScan / RuleEngine / LLMJudge / AuditTow）
- `packages/services/omnicompany/agent_team_demo.py` — Agent Team 4 Worker（Context / LLM / Tool / Finalizer · 含子 job 示例）
