<!-- [OMNI] origin=claude-code domain=standards ts=2026-04-18T00:00:00Z type=doc status=active -->
<!-- [OMNI] material_id="material:standards.global.distributed_docs_six_domain_placement.md" -->

# 分布式文档规范 v2

> **权威来源**：本文件。所有文档放置/拆分/归档决策以此为准，与其他规范冲突时以本文件为准。
> **必要不充分**：不满足一定有问题，满足不一定没问题。
> **Guardian 规则**：OMNI-030（禁版本化文件名）/ OMNI-031（测试后缀）/ OMNI-032（临时文件）/ OMNI-034（DESIGN.md 结构）/ OMNI-035（本规范合规性，待实施）
> **v2 要点**：全覆盖所有内容类型；明确尺寸/拆分/归档规则；`docs/design|gaps|legacy|reports` 重新归位到六域结构。
> **设施统一例外规则**: 核心设施/唯一权威收束类计划必须集中放置 `authority-confirmation.md` 与 `autonomous-execution-rules.md`; 分散 README / standards / templates / SKILL 只写短锚点指向它们。当前活跃样例见 authority-confirmation.md 与 autonomous-execution-rules.md。

---

## 一、总原则

1. **文档随内容走**——描述什么的文档，住在它描述的东西旁边。
2. **一类一处**——同一内容类型只有一个权威位置，不允许多地重复。
3. **尺寸即信号**——文档超过阈值就说明它在承担多个职责，必须拆分。
4. **索引而非复制**——跨域引用只写链接，不复制内容。
5. **生命周期可见**——每份文档的状态（draft / active / frozen / deprecated / archived）显式标注。

---

## 二、六域结构（全覆盖）

所有文档/准文档内容归到以下六域之一，没有第七域：

| 域 | 描述 | 根位置 |
|---|---|---|
| **A. 代码内文档** | docstring / 注释 / OmniMark 头 | 源文件内部 |
| **B. 就近文档** | 包/服务/基础设施模块的设计与清单 | `src/omnicompany/**/DESIGN.md` + `.omni/` |
| **C. 核心规范** | 框架级规则、标准、理论基础 | `docs/standards/` + `docs/theory/` |
| **D. 状态与回顾** | 当前进度、历史回顾、能力缺口 | `docs/PROGRESS.md` + `docs/reports/` + `docs/gaps/` |
| **E. 过程记录** | 一次性设计/调研/重构计划 | `docs/plans/<主题区>/[YYYY-MM-DD]TOPIC/` (主题区: 代码模块名 \| 业务域名 \| `omnicompany-<能力名>`) |
| **F. 工具与索引** | skills / 索引 / 架构图 / 机器可读配置 | `.claude/skills/` + `docs/README.md` + `docs/archmap.yaml` + `docs/taxonomy.yaml` |

> **边界清晰**：C 是"永远成立的规则"，D 是"此时此刻的状态"，E 是"一次性工作笔记"。新写文档时先问"它属于哪一域"，答不上就暂停。

---

## 三、内容类型矩阵（权威清单）

每个内容类型只能在一个位置出现。未列类型默认禁止新增。

| # | 内容类型 | 放置路径 | 文件格式 | 尺寸（软/硬） | 生命周期 |
|---|---|---|---|---|---|
| 1 | 模块 docstring | 源文件顶部 | Python/TS docstring | — | 与代码同步 |
| 2 | OmniMark 头 | 源文件/文档第一行 | `<!-- [OMNI] ... -->` | 单行 | 随内容更新 |
| 3 | 行内注释 | 代码旁 | `#` / `//` | — | 随代码 |
| 4 | 包/服务设计 | `src/omnicompany/packages/**/<pkg>/DESIGN.md` | Markdown + OmniMark | 300 / 500 行 | draft → active → deprecated |
| 5 | 基础设施模块设计 | `src/omnicompany/{bus,cli,core,dashboard,primitives,protocol,runtime/*,tools,tracing}/DESIGN.md` | 同上 | 同上 | 同上 |
| 6 | 包清单 | `src/omnicompany/**/<pkg>/.omni/manifest.yaml` | YAML + OmniMark | 80 / 150 行 | 随包演进 |
| 7 | 包健康档案 | `src/omnicompany/**/<pkg>/.omni/health/*.jsonl` | JSON Lines | — | 自动写盘 |
| 8 | Format 定义（代码邻） | `src/.../knowledge/formats/**/*.md` | Markdown + OmniMark | 100 / 200 行 | 与 format 类同步 |
| 9 | Router 定义（代码邻） | `src/.../knowledge/routers/**/*.md` | Markdown + OmniMark | 100 / 200 行 | 与 router 类同步 |
| 10 | 域/包根 README | `src/omnicompany/README.md` 仅此一处 | Markdown | 100 行 | 随导航需求更新 |
| 11 | 框架规范 | `docs/standards/<topic>.md` | Markdown + OmniMark + 强制度词 | 400 / 600 行 | frozen 优先 |
| 12 | 框架理论/基础设想 | `docs/theory/<topic>.md` | Markdown + OmniMark | 600 / 1000 行 | 季度复审 |
| 13 | L2 行为规范 | `docs/控制结构.md`（唯一） | Markdown | 200 / 300 行 | 超标即拆 standards |
| 14 | 架构全景图 | `docs/ARCHITECTURE.md` + `docs/archmap.yaml` | Markdown + YAML | 200 / 400 行 | 随架构变化 |
| 15 | SDK 合约 | `docs/SDK_CONTRACT.md` | Markdown | 200 / 400 行 | 版本化管理 |
| 16 | 词汇表 | `docs/taxonomy.yaml` | 机器可读 YAML | 300 / 500 行 | Guardian 消费 |
| 17 | 架构变更日志 | `docs/ARCH-CHANGES.jsonl` | JSON Lines | 单行累加 | append-only |
| 18 | 全局进度 | `docs/PROGRESS.md`（唯一） | Markdown | 400 / 500 行 | 按月归档 |
| 19 | 历史回顾报告 | `docs/reports/[YYYY-MM-DD]TOPIC.md` | Markdown + OmniMark | 600 行软，无硬限 | 写定即 frozen |
| 20 | 月度进度存档 | `docs/reports/progress/YYYY-MM-archive.md` | Markdown | — | 自动从 PROGRESS 归档 |
| 21 | 能力缺口清单 | `docs/gaps/INDEX.md` + `docs/gaps/G#_<slug>.md` | Markdown + OmniMark | 300 / 500 行/项 | 能力补足即 resolved |
| 22 | 过程/计划文档 | `docs/plans/<主题区>/[YYYY-MM-DD]TOPIC/plan.md` + 附属 (主题区命名见 §5.3) | Markdown + OmniMark | 500 / 800 行 | active → archived |
| 23 | 后台待办（L2） | `docs/overseer_backlog.md` | Markdown | 200 / 400 行 | 补完就删 |
| 24 | 总索引 | `docs/README.md`（**必备**） | Markdown | 150 行 | 新目录必更新 |
| 25 | 项目级 skill | `.claude/skills/<skill-name>/SKILL.md` + `reference/` | Markdown | 500 / 800 行 | 随能力演进 |
| 26 | 工作区根指引 | `E:\WindowsWorkspace\CLAUDE.md` | Markdown | 200 / 300 行 | 超标拆子页 |
| 27 | 用户自动记忆 | `~/.claude/projects/<proj>/memory/MEMORY.md` + `<type>_<slug>.md` | Markdown + frontmatter | 索引 200 行硬限 | 由 auto-memory 管理 |
| 28 | 供应商嵌入材料 | `src/omnicompany/packages/vendors/<name>/` | 按供应商约定 | — | 免合规，冻结 |
| 29 | 坟场标记 | `src/omnicompany/_graveyard/**/{_RETIRED.md,README.md}` | Markdown | 100 行 | 只增不减 |
| 30 | 技术债登记处 | `docs/tech_debt/REGISTRY.md`（唯一） | Markdown | 600 / 1000 行 | 持续追加；resolved 转末节 |

**凡表中未覆盖的内容类型，提案增补到本规范后再写**——不得自行新建 `docs/` 子目录。

---

## 四、放置规则（目录白名单）

### `docs/` 允许的直接子项（闭集）

```
docs/
├── README.md              # 总索引（新增必备）
├── PROGRESS.md            # 全局进度唯一权威
├── 控制结构.md            # L2 行为唯一权威
├── ARCHITECTURE.md        # 架构全景
├── SDK_CONTRACT.md        # 对外合约
├── overseer_backlog.md    # L2 顶班待办
├── taxonomy.yaml          # 机器可读词汇表
├── archmap.yaml           # 机器可读架构图
├── ARCH-CHANGES.jsonl     # 架构变更日志
├── standards/             # 框架规则
├── theory/                # 跨包理论/愿景（替换旧 design/）
├── reports/               # 历史回顾 + 月度进度存档
├── gaps/                  # 能力缺口清单
├── plans/                 # 一次性过程记录
└── tech_debt/             # 技术债统一登记处
```

**禁止**在 `docs/` 直接新增 `.md` 文件（除非增到上述闭集）。
**禁止** `docs/design/`、`docs/legacy/` 新增内容（v2 废弃，迁移见 §九）。

### `src/` 允许的文档位置

```
src/omnicompany/
├── README.md                               # 包根 README（唯一）
├── {bus,cli,core,dashboard,primitives,
│  protocol,runtime/<mod>,tools,tracing}/
│    └── DESIGN.md                          # 基础设施模块设计
├── packages/
│   ├── domains/<domain>/DESIGN.md
│   ├── domains/<domain>/<subpkg>/DESIGN.md
│   ├── domains/<domain>/PROGRESS.md       # ❌ 禁止（唯一 PROGRESS 在 docs/）
│   ├── services/<svc>/DESIGN.md
│   ├── services/<svc>/.omni/manifest.yaml
│   ├── services/<svc>/.omni/health/*.jsonl
│   ├── **/knowledge/formats/**/*.md        # format 定义
│   ├── **/knowledge/routers/**/*.md        # router 定义
│   └── vendors/<name>/**                   # 供应商免合规区
└── _graveyard/**/{_RETIRED,README}.md
```

**禁止**在 `src/` 下出现：
- 任意散文形式 `.md`（如 `NOTES.md`、`TODO.md`、`PLAN.md`、自由命名）
- `PROGRESS.md`（PROGRESS 权威只在 `docs/PROGRESS.md`）
- 额外的 `.yaml` 配置（manifest.yaml 之外的 YAML 需走代码审查新增）
- `docs/` 子目录

### `.claude/` 允许结构

```
.claude/
└── skills/<skill-name>/
    ├── SKILL.md
    └── reference/<resource>.md
```

禁止 `.claude/` 下出现其他类型文件（settings 在用户/项目级 `.claude/settings.json`，不在此规范范围）。

---

## 五、文件格式规范

### 5.1 OmniMark 头（**强制**）

所有第 4、5、6、8、9、11、12、19、21、22 类文档第一行必须是 OmniMark 头：

```markdown
<!-- [OMNI] origin=<source> domain=<domain> ts=<ISO8601> type=<type> status=<status> -->
```

- `type`：`doc` / `manifest` / `format` / `router` 之一（见 `omni-header.md`）
- `status`：`skeleton` / `draft` / `design` / `active` / `frozen` / `deprecated` / `archived`
- `domain`：对齐 `taxonomy.yaml` 的域清单

豁免：第 10、24、26、27、28、29 类（README、索引、workspace 根、记忆、供应商、坟场）。

### 5.2 DESIGN.md 结构（自我叙事三件套规范）

遵循 `protocol/self_narrative_three_files.md` §五（模板细则见 `design_md_template.md`）：
状态 / 核心接口 / 架构决策 / 数据流-拓扑 / 已知局限 / 参考资料，可选 内部构成 / 接收意愿。
「核心目的」由同目录 README.md 承载，不写进 DESIGN（2026-06-13 起以三件套为现行权威）。

### 5.3 plans/ 结构 (主题区单轴 + omnicompany- 行政层前缀, 2026-05-15 立)

```
docs/plans/
├── <主题区名>/[YYYY-MM-DD]TOPIC/      ← 代码模块或业务域主题区
├── omnicompany-<能力名>/[YYYY-MM-DD]TOPIC/  ← 行政层 (管公司本身, 不绑业务)
└── _archive/                          ← 仅放尚未归类到主题区的早期遗留
```

#### 主题区分类标准 (三种, 互斥)

每个 plan 属于且仅属于一个主题区。判定按下列顺序问:

1. **代码模块** — 计划在改/建一段具体代码 (例: agent-framework / dashboard / diagnosis / format-material / guardian / stage-experiments)
   - 顶层目录名 **必须 match `src/omnicompany/.../` 实际目录名**, 不取别名
   - 多代码模块都改时, 取改动量最大的那个主题区

2. **业务域** — 计划服务于具体业务域 (例: voxelcraft / demogame)
   - 顶层目录名 **必须 match `src/omnicompany/packages/domains/<domain>/` 实际目录名**

3. **omnicompany- 行政层** — 计划讨论方法论/元能力, 不绑死任何单一代码模块也不绑业务 (例: `omnicompany-计划跟进/` / `omnicompany-调研吸收/`)
   - 顶层目录名 **必须以 `omnicompany-` 开头**, 后接中文能力名
   - 行政层 = 管公司本身的工作, 不负责具体业务
   - 当前五个能力候选: `计划跟进` / `生成改进` / `体验评估` / `调研吸收` / `总结发布`

判定不出来时, 顺序优先级: 代码模块 > 业务域 > 行政层。即"能落到代码就落到代码, 不强行抽象到元层"。

#### 主题区内子层

允许多层关系, 但**子层必须继续按对象拆**, 不按时间轴/阶段/状态拆:

- ✅ `agent-framework/team-builder/[date]TOPIC/` — 按代码子模块拆
- ✅ `voxelcraft/N3-block-path/[date]TOPIC/` — 按业务子项目拆
- ❌ `voxelcraft/_milestones/[date]TOPIC/` — 按时间轴拆 (milestones 是状态不是对象)
- ❌ `agent-framework/_research/[date]TOPIC/` — 按性质拆 (用 plan 内部 tag 表达)

子层目录名同样要 match 代码或业务的实际子模块名。

#### 每个 plan 目录的内部结构

```
[YYYY-MM-DD]TOPIC/
├── plan.md          # 主文档 (必备)
├── decisions.md     # 可选, 决策沉淀
├── spikes/          # 可选, 调研笔记
├── brief.md         # 可选, 核心摘要 (退出条件/当前阶段/执行约束) 给 agent compact 后载入
└── _archive/        # 可选, 本 plan 内部归档
```

#### 归档

- 各主题区自带 `_archive/` 装本主题区已归档的 plan
- 顶层 `_archive/` 仅放尚未归类到主题区的早期遗留 (~70 项 2026-04 之前的 plan, 后续逐步分类入主)
- 新归档的 plan 必须落到所属主题区的 `_archive/`, 不再扔到顶层 `_archive/`

#### 禁律

- 禁止在 `plans/` 顶层散放 `.md` 文件
- 禁止顶层目录名是别名或简写 (必须 match 实际代码/业务/能力名)
- 禁止行政层目录省略 `omnicompany-` 前缀
- 禁止主题区下用时间轴/阶段/状态作为子层划分

### 5.4 reports/ 命名

```
docs/reports/[YYYY-MM-DD]TOPIC.md           # 一次性回顾
docs/reports/progress/YYYY-MM-archive.md    # 月度进度存档
```

历史回顾报告写定即 frozen——不修改，只新增。

### 5.5 标准文档必备段

`docs/standards/<topic>.md` 起首必须有：
- 状态（active / frozen / draft）
- 权威来源声明
- 必要不充分声明
- 强制度词汇定义（MUST / SHOULD / MAY）

---

## 六、尺寸与拆分触发器

### 6.1 阈值

每类文档的软/硬阈值见 §三矩阵。通用判据：

- **软阈值（warn）**：Guardian 扫描输出 LOW 级提醒
- **硬阈值（enforce）**：Guardian 输出 HIGH，PR 应拒绝合入除非带拆分计划

### 6.2 拆分触发器（客观信号）

满足任一即应拆分：

1. **行数超硬阈值**
2. **节数超过 10 个一级标题**
3. **混合三类以上主题**（如一份 standards 同时讲 A 规则、B 规则、C 背景理论）
4. **TOC 需要超过 30 行才能列完**
5. **同一段内 TBD / 待填 超过 5 处**（说明职责太杂还没想清）

### 6.3 拆分执行规则

- 框架规范（`docs/standards/`）：按主题拆为 `<topic>_<aspect>.md`，原文件保留主索引链回子文件
- 理论文档（`docs/theory/`）：按版本或子主题拆；旧版保留状态 `frozen`
- 计划（`docs/plans/`）：拆为子计划目录或按阶段切分 `plan.md` / `phase2.md`
- DESIGN.md：若单包设计>500 行，考虑该包应否拆子包
- PROGRESS.md：超 500 行 → 最旧条目移入 `docs/reports/progress/YYYY-MM-archive.md`

---

## 七、生命周期与归档

### 7.1 状态机

```
skeleton → draft → active → frozen → deprecated → archived
                          ↘ deprecated ↗
```

- **skeleton**：仅占位，允许多处 TBD
- **draft**：设计中，至少核心目的已填
- **active**：对应实现稳定运行
- **frozen**：已锁定不再大改（历史报告、已签稳定规范）
- **deprecated**：标记即将或已经被替代
- **archived**：迁入对应 `_archive/`，保留可追溯性

### 7.2 归档路径

| 内容 | 归档位置 |
|---|---|
| 完成的 plans | `docs/plans/_archive/[YYYY-MM-DD]TOPIC/` |
| PROGRESS 旧条目 | `docs/reports/progress/YYYY-MM-archive.md` |
| 废弃的 standards/theory | 标 `status=deprecated` 保留原位，1 季度后移 `docs/_archive/standards|theory/` |
| 废弃的代码及其 DESIGN.md | 整体移 `src/omnicompany/_graveyard/<path>/` |

### 7.3 plans 归档触发

- plan.md 标 `status=archived`
- 核心决策已迁入对应包 DESIGN.md 或 standards/（**必须**，否则不能归档）
- 目录整体移 `docs/plans/_archive/`

---

## 八、交叉引用与索引

### 8.1 `docs/README.md`（必备总索引）

所有 `docs/` 一级子项（含目录和文件）都要在 `docs/README.md` 有一行索引，格式：

```markdown
- 路径 — 一句话用途 — 所有者/权威
```

单文件不超过 150 行；超 150 行说明 `docs/` 根项太多，先整合。

### 8.2 引用规则

- 跨文件引用用相对链接：`standards/concepts/material.md`
- 禁止复制规则原文——只能引用
- plans → DESIGN.md 的回指：plan.md 归档前必须在对应 DESIGN.md 的"参考资料"节补上链接

### 8.3 发现性

- 新建包：DESIGN.md + .omni/manifest.yaml 同时创建
- 新建 standards/theory：`docs/README.md` 同时更新
- 新建 plans 目录：`docs/PROGRESS.md` 新增一行指针

---

## 九、v1→v2 迁移映射

现有违规内容的强制归位路径：

| 现状 | 归位 | 操作 |
|---|---|---|
| `docs/design/大迁移路线图.md` | `docs/theory/大迁移路线图.md` | 整体迁入 theory/ |
| `docs/design/六元语义*.md`（3 份） | `docs/theory/六元语义/` | 聚合为子目录 |
| `docs/design/pain_as_semantic_structure.md` | `docs/theory/` | 迁入 theory/ |
| `docs/design/用户语义信号需求.md` | `docs/theory/` | 迁入 theory/ |
| `docs/design/验收与进化路线图.md` | `docs/theory/` | 迁入 theory/ |
| `docs/legacy/legacy_index.html` | `docs/_archive/legacy/` | 纯历史留存 |
| `docs/reports/EVOLUTION_ENGINE_SUMMARY.md` 等无日期报告 | 添 `[YYYY-MM-DD]` 前缀或迁 theory | 按内容判断 |
| `docs/reports/progress/` 已存在 | 保留 | 符合 v2 |
| `docs/reports/sync/` | 删空目录或保留占位 | 验证是否使用 |
| `docs/plans/20260403_统一CLI基础设施` | `docs/plans/_archive/[2026-04-03]UNIFIED-CLI-INFRASTRUCTURE/` | 重命名+归档 |
| `docs/plans/claude code学习` | `docs/plans/_archive/[2026-04-XX]CLAUDE-CODE-LEARNING/` | 重命名+归档 |
| `docs/plans/*.md`（散文文件） | `docs/plans/[date]TOPIC/plan.md` | 包成目录 |
| `docs/plans/` 早于 2026-04-10 的多数目录 | `docs/plans/_archive/` | 批量归档（核心决策先回流 DESIGN.md） |
| `src/omnicompany/packages/domains/voxelcraft/PROGRESS.md` | 并入 `docs/PROGRESS.md` | 删源文件 |

---

## 十、Guardian 检测规则映射

| 规则 ID | 检测内容 | 本规范节 |
|---|---|---|
| OMNI-030 | 禁版本化文件名 | §5.1 |
| OMNI-031 | 测试文件命名 | — |
| OMNI-032 | 临时文件位置 | §四 src 禁区 |
| OMNI-034 | DESIGN.md 七节结构 | §5.2 |
| OMNI-035 | 本规范合规性（**待实施**） | 扫描：目录白名单 / 尺寸阈值 / OmniMark 头覆盖 / README 索引完整性 |

OMNI-035 实施前，人工审查 + CI grep 作为临时方案。

---

## 十一、优先级与状态

```
当前版本：v2（2026-04-18）
上一版本：v1（2026-04-13，保留在 git 历史）

P0（立即）：按 §九 迁移既有违规内容
P1（近期）：docs/README.md 总索引补齐；新建 docs/theory/
P2（中期）：plans/ 批量归档；核心决策回流 DESIGN.md
P3（长期）：OMNI-035 Guardian 规则实施
```

---

## 十二、冲突仲裁

- 本文件与其他 `docs/standards/*.md` 冲突 → 以本文件为准
- 本文件与 `docs/控制结构.md` 冲突 → 以 `控制结构.md` 为准（L2 行为优先）
- 本文件与 `CLAUDE.md` 冲突 → 以本文件为准，同步更新 CLAUDE.md
