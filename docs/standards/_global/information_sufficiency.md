# 信息充分性保障体系

> 状态：设计中（2026-04-14）  
> 触发：absorption Stage 3 SpecParser 遗漏 P0 发现，根因归结为系统性"信息空间有误"  
> 目标：99% 的信息充分性问题可在 LLM 体系内自行发现并解决

---

## 一、问题根源

### 1.1 "100 补丁"反模式

当前常见的失败路径：

```
运行 → 发现问题 → prompt 里加一条说明 → 再运行 → 发现另一个问题 → 再加一条
→ 最终：一个 prompt 里有 100 条"注意/补充/特别说明"
```

这是在用**症状修复**代替**根因修复**。根因几乎总是：这个节点拿到的信息不足以支撑它要做的判断。

不是"LLM 不聪明"，是"信息空间设错了"。

### 1.2 信息缺失的四个常见类型

| 类型 | 定义 | 本次例子 |
|---|---|---|
| **体系信息**（Static Context） | 操作对象的当前状态/能力/接口文档 | SpecParser 不知道 OmniCompany 有什么/缺什么 |
| **动态信息**（Dynamic State） | 同一 session 内"我已经做了什么" | SpecParser 不知道自己已提了 PRO-003 |
| **学习对象完整性**（Source Completeness） | 输入信息是否被过滤/裁剪过 | 只看到提案章节，没看到完整 findings 列表 |
| **原理/目标**（Why） | 这个节点的存在意义是什么 | SpecParser 不知道提案的目的是"补 G1-G7 缺口" |

### 1.3 F-14 的现有局限

F-14（format.md）规定"判断节点的输入信息必须足以支撑判断"。  
但 F-14 目前只检查 **Format 层面**（字段是否存在），不检查 **信息语义层面**（字段里的内容是否足够 LLM 做出可靠判断）。

需要一个更深的版本：**F-14b——信息充分性不只是字段存在性，是语义充分性**。

---

## 二、三层防御体系

### Layer 1：提前规避（Pre-design Checklist）

**在设计节点时，逐一回答五个问题：**

| 问题 | 对应信息类型 | 如果答不上来 |
|---|---|---|
| 这个节点为什么存在？做这件事的完整理由是什么？ | Why / 原理 | 节点目标不清晰，先不要设计 |
| 它从哪里获取完整的输入信息？上游是否裁剪过？ | Source Completeness | 检查 Format 链，确保不丢信息 |
| 它需要对照什么现有状态做判断？（当前系统能力？已有结果？） | Static Context | 把对照对象显式加入 FORMAT_IN 或 CONTEXT |
| 它需要知道"同一 session 内已做过什么"吗？ | Dynamic State | 设计节点内部状态或在 Format 中携带历史 |
| 判断粒度是否匹配？（要求粗粒度但传了原始代码）| Granularity | 在上游节点做摘要或在 prompt 指定粒度 |

**这个 checklist 是每个新节点设计的必填项**，附在 DESIGN.md 或节点旁边。

---

### Layer 2：运行时诊断（假运行 / 双轨）

**已有设计（本项目早期规划）**，尚未实现。

**假运行（Dry Run）**：节点不做主要工作，只做"我有没有足够的信息做这件事"的元分析，输出结构化诊断报告：

```python
DryRunReport = {
    "node_id": str,
    "information_gaps": [
        {
            "gap_type": "missing_context | incomplete_source | missing_why | stale_state",
            "description": "缺少 OmniCompany 自画像，无法判断提案适用性",
            "severity": "critical | major | minor",
            "suggested_source": "absorption.request.self_portrait",
        }
    ],
    "confidence_if_run": float,  # 0-1，LLM 估计的"就这些信息能做到什么程度"
    "recommendation": "block | warn | proceed",
}
```

**双轨运行（Dual-track）**：同时做 Dry Run 分析和实际运行。实际运行结果和诊断报告一起输出。人类或下游节点可以用诊断报告来判断实际结果的可信度。

**关键**：Dry Run 不是"试着跑一下看有没有报错"，是"用 LLM 分析自己的输入是否充分"。这本身也是一次 LLM 调用，prompt 是："给你这些输入，如果让你做 X，你觉得有哪些关键信息缺失？"

---

### Layer 3：动态兜底（Agent Loop 试探）

**当 Dry Run 发现信息缺口时，触发 Agent Loop 去找信息。**

Agent Loop 配置：
```python
InformationGatheringLoop = {
    "max_turns": 10,
    "tools": [
        "read_omnicompany_file",     # 读 OmniCompany 现有代码/文档
        "search_omnicompany",        # grep/glob OmniCompany 源码
        "read_session_context",      # 读当前 session 已有输出
        "ask_human",                 # 超出能力时上报人类（最后手段）
    ],
    "termination": {
        "found": "将找到的信息注入输入，继续主要工作",
        "not_found_after_N": "上报人类 + 记录 InformationRequestEvent",
    }
}
```

**这个 Agent Loop 的目标不是做主要工作，是找到做主要工作所需的信息。**  
找到后，主要工作照常进行（不再需要 Agent Loop）。

---

## 三、节点信息规范（扩展 FORMAT 标准）

> **2026-04-18 更新**：本节的 `REQUIRED_CONTEXT / KNOWN_SOURCES` 方案**已被 F-15 / P-13 取代**。
> 新规则明确禁止"超出 FORMAT_IN 的部分"靠 `input_data` 透传（详见 `format.md` F-15 + `pipeline.md` P-13）。
>
> 正确做法：
> - 若字段属于上游 Format 的语义 → 扩 FORMAT_IN 对应 Format 的 schema
> - 若字段是独立语义 → 拆独立 Format + `FORMAT_IN = list[str]` 做 fan-in
>
> 以下示例保留仅作历史参考，**不要用这种写法**。

```python
# ⚠️ 历史示例，已被 F-15/P-13 取代，不要学这种写法
class SpecParserRouter(Router):
    FORMAT_IN = "absorption.report.v3"
    FORMAT_OUT = "absorption.proposal.list"

    # 旧方案（已废弃）：声明额外需求，期望上游透传
    REQUIRED_CONTEXT = [
        "self_portrait",              # OmniCompany G1-G7 缺口（判断适用性）
        "findings",                   # 完整发现列表（不只是提案章节）
    ]
    KNOWN_SOURCES = {
        "self_portrait": "absorption.request（V3 管线入口字段，需透传）",
        "findings": "absorption.learning（LearningExtractor 输出，需透传）",
    }
    FALLBACK_BEHAVIOR = "trigger_information_gathering_loop"  # 信息不足时触发 Layer 3
```

字段的**旧**意义：
- `REQUIRED_CONTEXT` — 声明节点做出可靠判断所需的信息（"超出 FORMAT_IN 的部分"）→ **改为扩 FORMAT_IN 的 schema 或 fan-in**
- `KNOWN_SOURCES` — 如果 FORMAT_IN 里没有，去哪里找 → **改为 `FORMAT_IN = list[str]` 显式 fan-in**
- `FALLBACK_BEHAVIOR` — 信息仍然不足时的处理方式 → **此条仍有价值**（见下文 AgentLoop Fallback）

---

## 四、回顾既有工作流

**用 Pre-design Checklist 重新审查 absorption-v3 各节点：**

| 节点 | Why | Source Complete | Static Context | Dynamic State | 粒度 | 风险 |
|---|---|---|---|---|---|---|
| RepoMapper | ✅ | ✅ | N/A | N/A | ✅ | 低 |
| ModuleExplorer | ✅ | ✅ | ⚠️ 缺 OmniCompany 当前能力（依赖 self_portrait 但 self_portrait 质量不稳定） | ✅（补充模式有历史）| ✅ | 中 |
| LearningExtractor | ✅ | ✅ | ⚠️ 同上 | N/A | ✅ | 中 |
| ReportWriterV3 | ✅ | ✅ | ⚠️ 不了解 OmniCompany 现有结构（导致措辞失真）| N/A | ✅ | 中 |
| SpecParserRouter | ⚠️ 知道"提炼提案"但不知道"为什么提（补 G1-G7）"| ❌ 只看到提案章节 | ❌ 无 self_portrait | ❌ 无已生成提案状态 | ✅ | **高** |
| HumanApprovalGateS3 | ✅ | ✅ | N/A | N/A | ✅ | 低 |
| WorkflowGenerator（待实现）| ？ | ？ | ？ | ？ | ？ | 待评估 |

**发现**：SpecParserRouter 是当前信息充分性风险最高的节点，四个维度里三个有问题。

---

## 五、全自动场景的终态设计

目标：全自动运行时，99% 的信息问题在 LLM 体系内自解决。

**决策树（每个节点运行前）**：

```
节点触发
  ↓
Layer 1 Dry Run（LLM 分析输入充分性）
  ├── confidence >= 0.8 → 直接运行（绿灯）
  ├── 0.5 <= confidence < 0.8 → 双轨运行（同时运行+标注低置信度）
  └── confidence < 0.5 → 触发 Layer 3 信息收集
                          ├── 找到信息 → 注入后重新 Dry Run
                          └── N 轮后仍缺失 → 上报人类（InformationRequestEvent）
                                             + 记录到 overseer_backlog
```

**关键约束**：
- Layer 3 Agent Loop 最多 10 轮，不能无限试探
- 上报人类必须带结构化的"我需要什么信息、我尝试了哪些来源、为什么找不到"
- 全程的置信度和信息缺口都要记录进 events.db，供后续分析

---

## 六、当前工作流的角色

**absorption 工作流现在是这套方法论的"测试对象"**：
- SpecParser 的信息充分性问题是已知的、可重现的
- 等方法论（Layer 1-3）稳定后，用它来验证：
  - Layer 2 Dry Run 能不能发现 SpecParser 的 4 个信息缺口？
  - Layer 3 Agent Loop 能不能自己找到 self_portrait 和 findings？
- 验证成功后才修 SpecParser

**不要在方法论稳定前修补 SpecParser**——修了就失去了测试对象。

---

## 七、核心认知：降维与符号完备性（2026-04-14 补）

### 7.1 根本问题的精确表述

信息充分性的理想状态是两个条件同时成立：

```
条件 A：输入信息包含所有输出信息（信息论意义上的充分）
条件 B：到 LLM 的时候，符号的非通用含义（隐含义）含量最低 + 所有必要符号齐全
```

条件 A 是"量"——信息够不够多。  
条件 B 是"质"——信息是否对 LLM 透明可解码。

两个条件同时满足，才能接近充分必要。

### 7.2 降维的含义

"降维"（Dimensionality Reduction）不是信息压缩，而是**将领域特定问题转化为通用问题**：

- 将专业术语转化为通用描述（PoolType → "根据种族和是否新UP推断的卡池类型"）
- 将隐喻展开为字面描述（"打标" → "给字段标注分类标签"）
- 将隐含信息显式化（"更新模式" → "不是从零生成，而是在已有版本基础上修改"）

降维之后，LLM 不需要知道"TavernPool 是什么"，只需要理解"给定这些规则，对这个结构做这件事"——这是通用认知领域可以处理的问题。

### 7.3 降维对谁有用

**设计者也需要降维**。设计 demogame 管线的人，如果没有对业务术语做过降维，写出来的 Format 描述会充满隐含义——不只是 LLM 看不懂，另一个设计者或六个月后的自己也看不懂。

降维是双向的：
- 设计者降维：帮助自己搞清楚这件事的通用本质是什么
- 输入降维：帮助 LLM 理解而不依赖领域背景知识

### 7.4 为什么实践上难以估量

即使理论框架清晰，实践上有几个根本难点：

**难点 1：不知道自己有什么隐含义**  
隐含义的特性就是"对知道的人来说不像隐含义"。写 Format 描述的人不知道哪些词对不了解这个领域的人是不透明的。这是"知识的诅咒"（Curse of Knowledge）。

**难点 2：无法枚举 LLM 的知识边界**  
LLM 对某个术语的理解可能和预期不同（知道这个词，但意思偏了；或者完全不知道）。这需要实验才能发现。

**难点 3：信息量和符号质量的权衡**  
追求"零隐含义"可能导致每个 Format 字段要附带大段解释，变得过于冗长而失去可维护性。  
合理的目标不是零隐含义，而是**关键路径上的隐含义最小化**——只有影响输出正确性的隐含义才需要展开。

**难点 4：降维是有损的**  
将"TavernPool PoolType 推断规则"转化为通用描述时，可能丢失某些细节或边界条件。降维后的描述不总是等价于原始业务知识。

### 7.5 实践方向

基于以上认知，可以做的事情（按可操作性排序）：

**可操作、效果可量化：**
- 对 Format 描述建立"外行可读性测试"：读描述，不借助其他知识，能否理解这个 Format 包含什么、不包含什么？
- 关键 LLM 节点的 prompt 里，显式地把术语解释内嵌（不依赖 LLM 已知这个词）

**可操作、效果依赖实验：**
- Dry Run：让 LLM 读节点的 Format + 描述，评估"需要什么额外知识才能完成这个任务"，看它发现了多少我们已知的缺口
- 对比实验：同一个任务，给和不给业务背景知识，看输出质量差距

**难以直接操作，需要积累：**
- 把业务规则显式地 Format 化（demogame.tavern_rules、demogame.field_type_rules）
- 建立"领域知识库"，让节点可以声明依赖并按需读取

---

## 八、核心困境与近期路线（2026-04-14 补）

### 8.1 两个叠加困境

**困境 1：无状态性（Statelessness）**  
管线里每个 LLM 节点是无状态的——没有记忆，没有连续的"我之前学到了什么"。每次调用都从零开始解码输入。这意味着任何隐含义都不会被"上一次运行时学到"来弥补，每次都重新暴露。

**困境 2：知识的诅咒（Curse of Knowledge）**  
对无状态对象，知识的诅咒更严重。有状态的人类设计者至少可以意识到"上次我跑失败，是因为 LLM 不知道 X"——积累了经验。无状态的 LLM 每次都是第一次，无法积累对自身盲区的认知。

**叠加效应**：不只是"设计者忘了传信息"，还有可能"设计者自己也不知道这个信息是必要的"。设计者和执行者的隐性知识共同构成了系统性盲区。

### 8.2 设计者先跑通的原则

**管线设计只是假说（Hypothesis）阶段。**

正确流程应该是：
```
设计者自己推导并试着跑通（类 AgentNodeLoop 思维）
    ↓ 记录跑通过程中遇到的"我需要知道什么才能做这一步"
    ↓ 把这些"需要知道什么"显式地编入 Format 和 Router 描述
    ↓ 落回严格管线定义
    ↓ 实际运行验证（不可避免的 trial）
    ↓ 反思差异 → 改进
```

这和 AgentNodeLoop 是相通的：AgentNodeLoop 本质上是"让节点在真实信息环境里试探，找到能完成任务的最小充分信息集"。

**设计阶段几乎 100% 出错是正常的——但不应该接受。**  
短期目标：通过 checklist 和强调，把设计阶段的错误率从"几乎 100%"降到"显著更低"，同时建立"试跑→反思→改进"的闭环。

### 8.3 近期行动计划（简单版）

**Step 1（立即）**：在节点设计 checklist 里加入降维/符号完备性检查，强调重要性。这是廉价的提升，不指望解决所有问题，但能减少已知类型的错误。

**Step 2（接下来）**：用 absorption SpecParser 作为第一个案例，走"设计者先跑通"流程——亲自设想 SpecParser 完成任务需要什么信息，补入 Format，再跑，记录差距。

**Step 3（之后）**：根据 Step 2 的差距，回来完善预先设计流程和 checklist。

### 8.4 元观察：我们现在做的就是这件事本身

我们现在在做的——发现信息充分性问题 → 思考根因 → 设计方法论 → 找巨人的肩膀——本身就是 OmniCompany 演进管线应该做的事情。我们在人工模拟那个管线的完整流程。

这意味着：我们的记录和发现，本身就是该管线的训练数据和设计输入。

### 8.6 巨人的肩膀：已找到的学术与工程参照（2026-04-14）

#### 最直接命中的三个

**SagaLLM（VLDB 2025）** — 论文级，有代码  
arxiv:2503.19511 / GitHub: genglongling/SagaLLM  
把"context loss"（节点丢失上游关键信息）列为多 agent 系统四大根本缺陷之一。解法：  
- 显式依赖图 D = {(oᵢ, oⱼ, cᵢⱼ) | oⱼ depends on oᵢ under condition cᵢⱼ}  
- 独立 validator agent 在运行时检查"前置条件是否满足"  
- Saga 补偿事务模式  
→ 这是 Design by Contract 在 LLM pipeline 上的严格落地，和我们设计的 Dry Run 思路几乎完全吻合。

**Google ADK "Scope by Default"** — 生产级，最成熟  
google.github.io/adk-docs/context/  
官方原则：每个 model call 和 sub-agent 默认只看"所需的最小上下文"。不足时用工具显式拉取，不默认泄洪。  
量化：typed context object（200-500 token）vs 全对话转发（5000-20000 token），前者效率高 10-40x。  
→ 这是我们"REQUIRED_CONTEXT + KNOWN_SOURCES"声明的生产级参照实现。

**DSPy（Stanford）** — 工具可用  
github.com/stanfordnlp/dspy  
Signature 声明节点 input/output 类型约束 + MIPROv2 自动 optimizer。把"给节点多少信息最优"从人工判断问题转化为可度量的优化问题——有 metric 就能自动优化每个节点的 prompt，无需手工判断"够不够"。  
→ 这是"充分必要"问题的自动化路径，是我们方法论的下一个演进方向。

#### 其他有价值的参照

- **Context Engineering Survey（arxiv:2507.13334）**：1400+ 论文综述，"context sufficiency"已成立学科
- **Contracts for LLM APIs（2024）**：概率 precondition/postcondition 规范，650 个真实违约实例分析
- **LLMLingua（Microsoft, ACL 2024）**：用 perplexity 识别"哪些 token 贡献信息熵最少"，即充分性度量的技术实现
- **Guardrails AI**：missing_info gap detection 模式，输出端验证可借用到输入端缺失检测
- **Anthropic 官方博客**：更长 context 往往让结果变差——noise > signal，与充分必要原则完全吻合

#### 核心结论

| 问题 | 最成熟解法 | 来源 |
|---|---|---|
| 如何设计（静态） | Scope by Default + 显式依赖声明 | Google ADK |
| 如何验证（运行时） | 依赖图 + 独立 validator agent | SagaLLM |
| 如何自动优化 | Signature + metric-driven optimizer | DSPy |
| 如何度量充分性 | Perplexity-based token importance | LLMLingua |

这三条结合：设计时声明依赖（ADK style）→ 运行时验证（SagaLLM style）→ 有 metric 时自动优化（DSPy style），基本覆盖我们需要的全部层次。

### 8.7 非 LLM 通用领域的成熟实践（2026-04-14）

#### 核心发现：所有成熟工业系统都在收敛到同一原则

> **把信息充分性的验证从运行时推向更早的阶段**（编译期 > 启动期 > 构建期 > 设计期），  
> 并且**主动报告缺口而非假设充足**。  
> 没有任何成熟系统依赖"下游自己去发现信息不够"这个路径。

这是对当前 LLM 管线状态的直接批判——我们目前完全在"下游自己去发现信息不够"的状态。

#### 最可借用的五个模式

**Design by Contract（Eiffel / Bertrand Meyer）**
- Precondition = 调用方的义务（我来调用你，我保证这些条件满足）
- Postcondition = 被调用方的义务（你来调用我，我保证这些结果给你）
- 关键：被调用方**有权拒绝**在 precondition 不满足时执行——这不是异常，是正确行为
- LLM 管线对应：节点可以合法地返回 `INFORMATION_INSUFFICIENT`，而不是静默输出低质量结果

**依赖注入（DI）Constructor Injection**
- 组件在构造时声明自己需要什么，容器在启动时验证所有依赖可满足
- 如果依赖找不到 → 容器启动失败，比运行时崩溃早得多
- LLM 管线对应：管线 build 时验证每个节点的 REQUIRED_CONTEXT 都有已知来源，没有来源就拒绝启动

**丰田 Andon 系统（制造业）**
- 工人在"信息不足以完成当前工序"时有权拉绳停线
- 85% 的激活在 60 秒内解决而不停线——主动暴露比静默继续更高效
- 哲学："让问题可见胜过假装信息充足继续生产"
- LLM 管线对应：任何节点都可以拉 Andon（返回 HALT + 结构化缺口报告），这不是失败，是正确行为

**医疗交接 SBAR / I-PASS**
- 接收方被要求**复述**交接内容，这是交接完成前的信息充分性主动验证
- 十年研究：低质量交接贡献约 80% 的不良事件
- LLM 管线对应：Dry Run = 让节点"复述"自己收到了什么、理解了什么、缺什么——就是 I-PASS 的 Synthesis 环节

**Data Contract（dbt + Great Expectations）**
- 上游签约承诺交出的数据满足特定约束，下游依赖承诺而非假设
- 每次 build 检查 contract，违反则阻断 transform
- LLM 管线对应：Format 定义 = 数据契约，REQUIRED_CONTEXT = 精确的 contract 条款

#### 检测时机对比

| 机制 | 检测时机 | 能否阻断 |
|---|---|---|
| 依赖类型系统（Idris/Agda） | **编译期** | 强 |
| DI 构造函数注入 | **容器启动期** | 强 |
| Schema Registry 兼容性 | **Schema 提交时** | 强 |
| DbC Precondition | **调用前** | 强 |
| Data Contract（dbt/GE） | **每次 build** | 中 |
| Andon 系统 | **工人判断时** | 强（停线） |
| SBAR 复述 | **交接完成前** | 中 |
| ICD Walkthrough | **设计里程碑** | 中 |
| MBSE 接口完整性 | **模型构建时** | 强（工具标记） |
| Data Lineage | **事后** | 无 |

LLM 管线目前在最右边：事后发现，无法阻断。目标是向左移。

#### 对 OmniCompany 的直接启示

从非 LLM 领域提炼三条对 OmniCompany 最可操作的原则：

1. **节点有权拒绝（Andon 原则）**：节点在信息不充分时应该返回结构化的 INFORMATION_INSUFFICIENT，而不是静默输出低质量结果。这是正确行为，不是失败。

2. **接口契约先于实现（ICD/DbC 原则）**：Format 定义必须先于 Router 实现，且 Format 必须精确到"消费方需要什么"而非"生产方能给什么"。

3. **验证越早越好（DI 原则）**：管线能在 build 时发现的缺口，不应该等到 run 时才发现。REQUIRED_CONTEXT 声明 + 启动期 dependency resolution 是这个原则的实现。

---

### 8.5 下一步：找巨人的肩膀

这个问题——**如何保证多步骤 LLM 管线中每个节点的信息充分性**——不是我们独有的挑战。它的等价形式出现在：

- **AI 工程**：Multi-agent 系统中的上下文传递、prompt chaining、RAG pipeline 设计
- **软件工程**：接口契约（Design by Contract）、信息隐藏原则、依赖倒置
- **管理学/工作流**：业务流程中的知识传递、handoff 设计、任务分解的信息完整性
- **信息论**：充分统计量、互信息、信道容量

需要主动寻找在 AI 领域、软件领域、通用领域对这类问题最先进的学术研究和工程实践。

---

## 九、原待做事项

- [ ] 设计 Dry Run 节点的具体实现（输入/输出 Format、LLM prompt 结构）
- [ ] 为 REQUIRED_CONTEXT / KNOWN_SOURCES / FALLBACK_BEHAVIOR 制定 Router 标准（更新 SKILL.md）
- [ ] 实现一个 InformationGatheringLoopRouter（通用 Layer 3 Agent Loop）
- [ ] 用 absorption SpecParser 作为 proof of concept：Dry Run → 发现 4 个缺口 → Agent Loop 找到信息 → 重跑 → 提案覆盖全部 P0 发现
- [ ] 把 Pre-design Checklist 加入节点设计流程（Doctor 可以用它做静态检查）
