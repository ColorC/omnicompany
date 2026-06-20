# spec 报告材料规范 · 2026-06-13

> 来源: 用户 2026-06-13 裁决"应有文档可看, 文档里有足够截图表明特性在何时发生, 有链接可跳其他材料,
> 演示与文档可双向链接, 可复制段落 id"。本规范是 webgame-spec 等主体型审阅材料里"文档"这一件的唯一权威。
> 上位: [review_report_form_association.md](../protocol/review_report_form_association.md)。

## 一句话

**spec 报告 = 一份围绕"主体"组织的 wiki-core 文档**: 截图标明每个特性在何时发生, 链向引导演示与文件树 diff 及其他材料, 段落可复制 id 供精确引用, 并承载导览三件套。它解答用户两类追问——"改了哪些文件、怎么改的"与"你的思路到底是什么"。

## 为什么

主体型产物围绕主体变化展开; 文档不是流水账, 而是让用户在有疑问时能**就地跳转**(去演示某一步、去看文件 diff、去引用某段问思路)。可复制段落 id + 双向链接是把"我对这段有疑问"变成一次精确定位的前提。

## 规范本体

### 形态(技术栈 / 接口)

- **文档 = wiki-core 文档**(Obsidian flavor markdown), 用 wiki-core `viewer` 渲染。复用其能力:
  - 标题锚点(`anchorPermalink`)、每段"复制段落 id"按钮(FNV-1a → `wiki://page#h=<hash>`)、反链面板。
  - 段落评论(`comments.js`, 与 dashboard `annotations.ts` 哈希逐字一致)。
- **双向链接**(复用 FNV-1a, 不另造锚点):
  - `wiki://<page>#h=<hash>` 段落锚点 · `demo://<tourId>#<stepId>` 演示步 · `mat://<mat_id>` 其他材料。
  - 文档内可链演示步与文件树 diff; 演示步的 `links` 也可回链文档段落 = 双向。

### 内容要求

1. **围绕主体**: 按主体的特性/改动组织, 不按"开发流水"组织。
2. **截图标时机**: 每个值得审的特性配截图(引用 `docs/reviews/<date>/` 的帧), 文字说明"它在什么操作后、什么时刻发生"。
3. **可跳转**: 改了哪些文件 → 链 `mat://` 文件树 diff 兄弟材料; 怎么体验 → 链 `demo://` 对应演示步; 思路细节 → 文档内分节展开, 段落可被 `wiki://...#h=` 精确引用。
4. **承载导览三件套**: 对应需求 / 完成度 / 体验路径(规范见 [审阅与推送规范.md](审阅与推送规范.md), 缺一不可)。

### 目录 / 命名 / 提交

- 文档源在 app `docs/wiki/`(或作为材料 `inline_content`); 截图引用 `docs/reviews/<date>-<slug>/`。
- 作为 `kind=webgame-spec` 父材料提交, `extra.demo` / `extra.doc` / `extra.filetree_diff` 给出三件套引用。父材料的 `inline_content` 即本 spec 报告 markdown。

### 三大禁忌

- 不散落: 截图只引 `docs/reviews/<date>/`, 文档只在 wiki 库/材料。
- 不旁路: 段落评论只走 reviewstage, 锚点只用 FNV-1a。
- 不重复造轮: 渲染/锚点/评论全复用 wiki-core, 不手写 markdown 渲染或新锚点算法。

### 中文-only gate

用户可见正文受中文-only gate。

## 适用 / 谁读

- **任何提交 webgame-spec 的 agent**。模板: [templates/spec报告.md](templates/spec报告.md)。
- 关联: [引导演示材料规范.md](引导演示材料规范.md)、[审阅与推送规范.md](审阅与推送规范.md)。
