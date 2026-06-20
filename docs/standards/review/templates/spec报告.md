# spec 报告模板

> 用法: 复制下面骨架填成 webgame-spec 父材料的 `inline_content`(wiki-core markdown 文档)。
> 规范见 [../spec报告材料规范.md](../spec报告材料规范.md)。

## 骨架(复制填写)

```markdown
# <主体名> · <本次主题> spec 报告

## 对应需求
<这次改动满足哪条需求 / 用户裁决。给出处。>

## 完成度
- 状态: <完成 | 部分 | 阻塞>
- 做了: <围绕主体的特性/改动逐条>
- 没做完 / 已知缺陷: <还差什么>

## 体验路径
1. <从哪进 → 链 demo://<tourId>#<stepId>>
2. <点/看什么>
3. <预期看到什么 = 验收点>

## 特性逐项(每个配截图标时机 + 链接)
### <特性 A>
![<说明>](../reviews/<date>-<slug>/<frame>.png)
- 何时发生: <什么操作后、什么时刻>
- 改了哪些文件: 见文件树 diff → mat://<filetree_mat_id>
- 思路: <分节展开, 本段可被 wiki://<page>#h=<hash> 精确引用>

## 链接索引
- 引导演示: demo://<tourId>
- 文件树 diff: mat://<filetree_mat_id>
- 相关材料: mat://<...>
```

## 落地清单

1. 文档用 wiki-core 渲染(标题锚点 + 复制段落 id + 反链均自带)。
2. 截图只引 `docs/reviews/<date>-<slug>/`。
3. 提交 `omni review submit --kind webgame-spec --content <本文> --extra-json '{"demo":"...","doc":"...","filetree_diff":"..."}'`。
4. 正文中文-only。
