
# OmniCompany

> 一个让 AI Agent **自己维护自己**的工厂：工作流自动学习编排 / 诊断修复 / 系统架构自维护。

本文件是进入 `src/omnicompany/` 的**顶层导航索引**。顺链可到达任何模块的 `DESIGN.md`、源码、以及相关规范。

---

## 一、能力分类（按领域）

OmniCompany 的核心能力可归为五类。每类对应一组模块，点进去读各自的 `DESIGN.md` 详述。

### 学习 · Learning

从外部仓库 / 自身运行经验 中提炼可操作的知识。

| 模块 | 做什么 | 文档 |
|---|---|---|
| `packages/services/absorption/` | 外部仓库吸纳（V3 管线：RepoMapper → ModuleExplorer → LearningExtractor → ReportWriter）| [DESIGN](packages/services/absorption/DESIGN.md) |
| `runtime/agent_crystallize/` | Agent 运行经验沉淀为 SpecPatch | [DESIGN](runtime/agent_crystallize/DESIGN.md) |
| `packages/services/hypothesis/` | 假设学习管线（Experimenter + Reflector 语义判断）| [DESIGN](packages/services/hypothesis/DESIGN.md) |
| `packages/services/trace_induction/` | 执行轨迹 → 模式归纳 | [DESIGN](packages/services/trace_induction/DESIGN.md) |
| `packages/services/pattern_discovery/` | 跨域模式发现 | [DESIGN](packages/services/pattern_discovery/DESIGN.md) |
| `packages/services/knowledge/` | OmniKB 知识库（假设文档 / SpecPatch 沉淀的归宿）| [DESIGN](packages/services/knowledge/DESIGN.md) |
| `packages/services/evolution/` | 管线/配置演化子系统 | [DESIGN](packages/services/evolution/DESIGN.md) |

### 诊断 · Diagnosis

对管线 / 代码 / 信息充分性做健康检查。

| 模块 | 做什么 | 文档 |
|---|---|---|
| `packages/services/doctor/` | 管线级健康诊断（Format/Router/Pipeline 三条诊断管线）| [DESIGN](packages/services/doctor/DESIGN.md) |
| `packages/services/guardian/` | 代码/文档规范自动巡逻（OMNI-001 ~ OMNI-034）| [DESIGN](packages/services/guardian/DESIGN.md) |
| `runtime/info_audit/` | 信息充分性四层机制（probe / piggyback / post_hoc / crystallize）| [DESIGN](runtime/info_audit/DESIGN.md) |
| `packages/services/selftest/` | 系统自测套件 | [DESIGN](packages/services/selftest/DESIGN.md) |
| `packages/services/lap_auditor/` | LAP 协议合规审计 | [DESIGN](packages/services/lap_auditor/DESIGN.md) |

### 执行 · Execution

管线/Agent 的运行引擎。

| 模块 | 做什么 | 文档 |
|---|---|---|
| `runtime/exec/` | PipelineRunner（DAG 执行、fan-in/out、join、retry、budget）| [DESIGN](runtime/exec/DESIGN.md) |
| `runtime/agent/` | AgentNodeLoop（多轮对话、四层压缩、工具权限）| [DESIGN](runtime/agent/DESIGN.md) |
| `runtime/llm/` | LLMClient（RateLimiter + 令牌桶 + 重试 + piggyback + tool_choice）| [DESIGN](runtime/llm/DESIGN.md) |
| `runtime/routing/` | Router 基类与内置 Router（Context/LLM/Tool）| [DESIGN](runtime/routing/DESIGN.md) |
| `runtime/nodes/` | 节点类型定义（ANCHOR/TRANSFORMER/SCATTER/JOIN 等）| [DESIGN](runtime/nodes/DESIGN.md) |
| `cli/` | 命令行入口（`omni pipeline / registry / diagnose` 等）| [DESIGN](cli/DESIGN.md) |
| `tools/` | 内置工具库（节点执行时的原子能力）| [DESIGN](tools/DESIGN.md) |
| `packages/services/registry/` | 运行时 Router / Format 注册与查询 | [DESIGN](packages/services/registry/DESIGN.md) |

### 持久化 & 观测 · Persistence

数据、事件、审计记录的落盘与查询。

| 模块 | 做什么 | 文档 |
|---|---|---|
| `bus/` | EventBus（SQLite 事件总线，管线观测入口）| [DESIGN](bus/DESIGN.md) |
| `runtime/info_audit/audit_store.py` | LLM 调用审计落盘（trace-id 分文件 jsonl）| [DESIGN](runtime/info_audit/DESIGN.md) |
| `runtime/storage/` | 通用存储抽象 | [DESIGN](runtime/storage/DESIGN.md) |
| `tracing/` | 链路追踪（事件采集底层依赖）| [DESIGN](tracing/DESIGN.md) |
| `dashboard/` | 可视化看板（管线运行 / 健康档案 / 审计）| [DESIGN](dashboard/DESIGN.md) |

### 规范 · Protocol

系统的契约层。不改这里，就不会走形。

| 模块 | 做什么 | 文档 |
|---|---|---|
| `protocol/` | LAP 核心协议（Anchor / Format / Transformer / Verdict / Route）| [DESIGN](protocol/DESIGN.md) |
| `core/` | 跨模块基础设施（dispatch / registry / config / guarded_write）| [DESIGN](core/DESIGN.md) |
| `primitives/` | 六元原语基础类（Signal / Hook 定义）| [DESIGN](primitives/DESIGN.md) |
| `runtime/signals/` | 信号原语实现（primitives 的运行时伴生）| [DESIGN](runtime/signals/DESIGN.md) |

> **跨类属性说明**：少数模块天然跨两类：`runtime/info_audit/` 同时承担诊断（probe）与持久化（audit_store.py），`runtime/routing/` 和 `packages/services/lap_auditor/` 同时贴近执行/诊断与规范 —— 归类按主要职责，不做重复列示。

---

## 二、业务域（应用层）

`packages/domains/` 下是**用管线+Router 解决实际业务问题**的模块。

| 域 | 做什么 | 主要子模块 |
|---|---|---|
| `gameplay_system/` | 游戏config_table学习 + Unity QA + 业务生成 | `table_learning/`, `unity_qa/`, `ux/` ([DESIGN](packages/domains/gameplay_system/ux/DESIGN.md)), `produce/`, `benchmark/` |
| `voxel_engine/` | 代码块演化 + 视觉 QA | `mechanics_evolver/`, `visual_qa/` |
| `creative_content/` | 叙事生成 + CSL | `routers/`, `tools/` |
| `software_engineering/` | 软件工程七阶段（plan/design/tdd/implement/review/verify/equiv_test）| 各阶段子包 |

详细索引见 [packages/domains/INDEX.md](packages/domains/INDEX.md)（_待补充_）。

---

## 三、管线目录

所有已注册的 pipeline 在 `core/registry.py`。查询入口：

```bash
omni pipeline list         # 列所有管线
omni pipeline show <id>    # 查单个管线结构
```

按命名空间：
- `absorption.*` — 吸纳系列（survey / v2 / v3 / v3-stage3）
- `doctor-*` — 三条诊断管线（format / router / pipeline）
- `hypothesis.*` — 假设学习
- `gameplay_system.*` / `voxel_engine.*` / `creative_content.*` — 各业务域

---

## 四、核心规范（Standards）

系统级铁律，所有模块必须遵守：

| 规范 | 路径 | 说明 |
|---|---|---|
| **LLM-first** | [llm_first.md](../../docs/standards/llm_first.md) | 智能→LLM，规则必须经 LLM 验证；**禁止预防性截断**；**预算宽松到触发即 bug** |
| **信息充分性** | [information_sufficiency.md](../../docs/standards/information_sufficiency.md) | 节点输入必须是最小充分信息集（F-14 原则） |
| **Format 体系** | [format.md](../../docs/standards/material.md) | FORMAT_IN/OUT 规范、parent 继承、composite 关系 |
| **Router 体系** | [router.md](../../docs/standards/worker.md) | FORMAT_IN/OUT/DESCRIPTION 三元，soft/hard 分界 |
| **Pipeline 体系** | [pipeline.md](../../docs/standards/team.md) | 管线构造、节点拓扑、路由规则 |
| **代码风格** | [code.md](../../docs/standards/code.md) | 命名、注释、安全 |
| **OmniMark 头** | [omni-header.md](../../docs/standards/omni-header.md) | 文件身份标记 |
| **分布式文档** | [distributed-docs.md](../../docs/standards/distributed-docs.md) | DESIGN.md + .omni/manifest.yaml + docs/ 层级 |
| **DESIGN.md 模板** | [design_md_template.md](../../docs/standards/design_md_template.md) | 本类文档的固定七节结构、TBD 约定、OMNI-034 规则 |

---

## 五、当前状态与缺口

- **当前主轴**：见 [docs/PROGRESS.md](../../docs/PROGRESS.md)（权威状态）
- **控制结构**：见 [docs/控制结构.md](../../docs/控制结构.md)（L2 行为规范）
- **已识别缺口**：见 [docs/gaps/INDEX.md](../../docs/gaps/INDEX.md)（G1-G7 详档，替代了之前硬编码在 input 里的 self_portrait 文字）

---

## 六、agent 使用本索引的方式

当一个 research agent / dispute loop / doctor 需要了解 OmniCompany 某模块时：

1. **从本 README 出发**，按"能力分类"锁定目标领域
2. 读对应模块的 `DESIGN.md` — 若 `status=active` 信任文档，若 `status=skeleton` 回源码
3. 顺 `## 参考资料` 链到源码做二次验证
4. 若发现某能力**没有对应 DESIGN.md 且也不在已识别缺口里** → 可能是 OmniCompany 不知道自己不知道的领域，写入 [docs/gaps/](../../docs/gaps/) 候选

本 README 遵循两大铁律：**不截断 + 信息空间完整可达**。所有内容通过链接延伸，不在一页里塞所有细节。

---

## 七、目录速查

```
src/omnicompany/
├── README.md              # ← 你在这里
├── protocol/              # LAP 核心契约
├── core/                  # 跨模块基础设施
├── primitives/            # 六元原语
├── runtime/               # 运行时引擎
│   ├── exec/             #   管线执行
│   ├── agent/            #   Agent 循环
│   ├── agent_crystallize/ #  经验沉淀
│   ├── info_audit/       #   信息审计
│   ├── llm/              #   LLM 客户端
│   ├── routing/          #   Router 基类
│   ├── nodes/            #   节点类型
│   ├── signals/          #   信号系统
│   └── storage/          #   通用存储
├── bus/                   # 事件总线（SQLite）
├── packages/
│   ├── services/         # 服务（诊断 / 学习 / 注册...）
│   └── domains/          # 业务域（gameplay_system / voxel_engine / creative_content / software_engineering）
├── cli/                   # 命令行入口
├── dashboard/             # 可视化
├── tools/                 # 内置工具库
└── tracing/               # 链路追踪
```
