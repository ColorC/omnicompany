<!-- [OMNI] origin=ai-ide domain=omnicompany/standards/_global ts=2026-05-02T06:00:00Z type=doc status=active agent=ai-ide-current -->
<!-- [OMNI] summary="obsidian wikilink + 统一 tag 字典规范, 跟 dashboard notes_api 已有 wikilink 实现 + plan.md 规范 v1 对齐" -->
<!-- [OMNI] why="用户原始需求 3.2: 全面正式化人类可观看文档库 — 集中使用 obsidian 格式 + 大量开始使用统一 tag" -->
<!-- [OMNI] tags=standard,obsidian,wikilink,tag,distributed-docs -->
<!-- [OMNI] material_id="material:standards.global.obsidian_wikilink_tag_dictionary.md" -->

# obsidian wikilink + 统一 tag 字典

> **状态**: 规范 v1 (2026-05-02), dashboard notes_api 已支持 wikilink, 现规范 + tag 字典
> **关联实装**: `dashboard/notes_api.py` (wikilink 解析 + 反向链接图) + `docs/standards/concepts/plan.md` (plan 规范 v1 已用 wikilink)
> **关联规范**: `distributed-docs.md` (六域结构) + `omni-header.md` (OmniMark 头)

## 一、 这是干嘛的

用户原始需求 3.2:

> "全面正式化人类可观看文档库 — 集中使用 obsidian 格式 + 大量开始使用统一 tag"

含义:
- 文档体系 (data + doc[plan/report]) 跟 obsidian (流行 markdown 笔记工具) 兼容
- wikilink (`[[name]]`) 作内部交叉引用主形式, 不用相对路径 markdown 链接
- 统一 tag 字典让跨文档检索 + 守护扫描有一致词表
- dashboard notes_api 已经实施 wikilink 解析跟反向链接图, 这层是规范跟字典

## 二、 wikilink 语法

### 基本形式 (跟 obsidian 一致, dashboard notes_api 已支持)

| 语法 | 含义 | 例 |
|---|---|---|
| `[[name]]` | 链接到 note 名为 name 的文档 | `[[plan-omnicompany-format-standardization]]` |
| `[[name\|alias]]` | 链接 + 自定义显示文字 | `[[plan-omnicompany\|本主题计划]]` |
| `[[name#heading]]` | 链接到文档的子标题 | `[[plan-omnicompany#架构决策]]` |
| `![[name]]` | 嵌入引用 (图片 / 文档) | `![[diagram.png]]` |

### 类型化 wikilink (omnicompany 扩展, 规范 v1 加, 跟 plan.md 规范一致)

dashboard 的 react-markdown remark-wikilinks 插件 应识别如下类型化前缀:

| 前缀 | 链接到 | 例 |
|---|---|---|
| `[[plan:<id>]]` | docs/plans/ 下的 plan | `[[plan:_infra/[2026-04-30]OMNICOMPANY-FORMAT-STANDARDIZATION]]` |
| `[[worker:<id>]]` | services 下的 worker | `[[worker:demogame.team_table.SchemaAssembler]]` |
| `[[material:<id>]]` | services 下的 material | `[[material:demogame.season_book]]` |
| `[[team:<id>]]` | services 下的 team | `[[team:csv_to_md]]` |
| `[[agent:<id>]]` | agent 实例 | `[[agent:demogame.business_researcher]]` |
| `[[hook:<id>]]` | hook 实例 | `[[hook:guardian.daily_health_check]]` |
| `[[tool:<id>]]` | tool 实例 | `[[tool:lark_cli]]` |
| `[[data:<id>]]` | data 实例 | `[[data:demogame.season_book_research]]` |
| `[[meta_io:<id>]]` | 元 IO | `[[meta_io:meta_io.fs.read_file_text]]` |
| `[[standard:<id>]]` | docs/standards/ 下的规范 | `[[standard:cli/lock]]` |
| `[[workspace:<path>]]` | 工作区路径 | `[[workspace:.omni/sandbox/drafts/data/foo]]` |
| `[[package:<id>]]` | 服务包 | `[[package:services._authoring.report_author]]` |
| `[[note:<id>]]` | 普通笔记 | `[[note:weekly-2026-w18]]` |
| `[[task:<id>]]` | 任务 | `[[task:fix-quota-quirk]]` |

无前缀 `[[name]]` 由 dashboard notes_api 用 fuzzy match 解析到最近 note. 类型化前缀避免歧义 + 让守护扫描能精准查 dependency.

## 三、 统一 tag 字典 (v1)

tag 用 hashtag 形式 (`#category/subcategory`) 嵌在 markdown 文档体, 也可在 OmniMark 头的 `tags=` 字段列出.

### 主类别 (`#category`)

| 主 tag | 用途 | 例子 |
|---|---|---|
| `#standard` | 规范文档 | `#standard/cli` `#standard/concept` `#standard/protocol` |
| `#concept` | 概念 / 八种基础类型 | `#concept/worker` `#concept/material` `#concept/agent` |
| `#plan` | 计划过程 | `#plan/active` `#plan/archived` `#plan/draft` |
| `#data` | 数据资产 | `#data/research` `#data/fact` `#data/observation` |
| `#feedback` | 用户反馈 | `#feedback/rule` `#feedback/methodology` |
| `#decision` | 决策记录 | `#decision/architecture` `#decision/naming` |
| `#bug` | 缺陷 | `#bug/resolved` `#bug/open` `#bug/wontfix` |
| `#task` | 任务 | `#task/todo` `#task/inprogress` `#task/done` |
| `#audit` | 审计 / 审查 | `#audit/security` `#audit/quality` |
| `#kb` | 知识库 | `#kb/business` `#kb/technical` |

### kind 子类别 (跟 omnicompany 8+1 概念一一对应)

| 子 tag | 适用文档 |
|---|---|
| `#kind/worker` | worker 文档 / 设计 / 注册件 |
| `#kind/material` | material 文档 |
| `#kind/team` | team 文档 |
| `#kind/agent` | agent 文档 |
| `#kind/hook` | hook 文档 |
| `#kind/tool` | tool 文档 |
| `#kind/data` | data 文档 |
| `#kind/plan` | plan 文档 |
| `#kind/meta_io` | 元 IO 文档 |

### 状态 tag

`#status/active` / `#status/draft` / `#status/deprecated` / `#status/archived` / `#status/wip`

### 业务域 tag

`#domain/demogame` / `#domain/voxelcraft` / `#domain/narrative` / `#domain/csv_to_md` / `#domain/<your-domain>`

### 优先级 tag

`#priority/blocker` / `#priority/major` / `#priority/minor` / `#priority/info`

## 四、 OmniMark 头跟 tag 的关系

文件头里 `tags=` 字段 (跟本规范字典一致) + 文档体里 hashtag (`#category/sub`):

```markdown
<!-- [OMNI] origin=ai-ide ts=2026-05-02 type=doc tags=standard,obsidian,wikilink -->

# 文档标题

#standard/cli  #priority/major

正文内容...
```

OmniMark 头 tags (无 `#`) 是机器扫描用 (守护 / 注册中心). 文档体 hashtag (含 `#`) 是 obsidian / dashboard 用. 两者**应当一致** (机器跟人看到同一组分类), 但语法形态不同.

dashboard notes_api 现在只解析 wikilink, 后续应加 hashtag 解析跟反向索引.

## 五、 反模式

**裸 markdown 链接代替 wikilink** — `name` 不进 wikilink 反向图. obsidian 兼容跟守护扫描都失效. 改用 `[[name]]`.

**自定义 tag 不在字典** — 例 `#omnicompany-2026-q2` 这种 ad-hoc tag, 短期看似清晰长期淹没. 加新 tag 先扩本字典.

**全用主类别 tag 不细化** — `#standard` 太宽, 应该 `#standard/cli` / `#standard/concept` 细化. 没层级的 tag 检索价值降到名字搜索一样.

**OmniMark 头 tags 跟文档体 hashtag 不一致** — 头说 `tags=plan,active`, 体里 `#draft` — 守护看一组, 人看另一组, 互相不知道.

**wikilink 用 fuzzy 名字而非类型化** — `[[lock]]` 可能匹配到 `lock.md` 也可能 `cli/lock.md`. 用类型化 `[[standard:cli/lock]]` 精准.

## 六、 跟 dashboard 联动

| 接口 | 内容 |
|---|---|
| `/api/notes` | 列所有 note (含 wikilink count) |
| `/api/notes/_links` | 反向链接图 |
| `/api/notes/{id}/links` | 单 note 出 / 入链 |
| `/api/notes/_search?q=` | 全文搜索 (含 hashtag) |

frontend 用 react-markdown + remark-wikilinks 渲染. 类型化 wikilink (例 `[[standard:cli/lock]]`) 由 frontend 的 KNOWN_TYPES 已支持.

## 七、 演进 (留下一阶段)

- **dashboard 加 hashtag 反向索引** — notes_api 当前只解析 wikilink, 加 hashtag 解析后可按 tag 过滤
- **守护扫 OmniMark 头 vs 文档体 tag 一致性** — 加一条规则到 guardian
- **tag 字典动态扩展** — 当前是静态 list, 后续走类似 EntityTypeDef.register_type 让业务域可注册自己的 tag
- **catalogue 跟 tag 联动** — `/api/teams?tag=#domain/demogame` 按 tag 过滤
- **跟 plan 规范 v1 binding 块整合** — 当前 plan binding 跟 tag 部分重叠
