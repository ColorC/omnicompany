# 审阅↔报告形态关联 · 基础规范宣告 · 2026-06-13

> 来源: 用户 2026-06-13 裁决"全部约束应通过设施化+prompt 双重保证执行, 确保材料在符合特定条件时触发特定审阅格式需求;
> 不同待审阅材料应有自己的规范; 后续新增待审阅材料主体类型也需仔细考虑如何呈现给用户实现最大化信息传递率"。
> 本文是该关联的基础契约。**其他主体类型的具体审阅规范现在不做**, 仅在此立总则与扩展协议。

## 一句话

**待审阅材料的"主体类型"决定它的"呈现形态"**。每种主体类型有自己的审阅规范与偏好, 目标是**最大化信息传递率**——让用户用最短路径看懂"对应什么需求、改了什么、怎么体验"。新主体类型投用前, 必须先声明其审阅形态。

## 双重保证(设施 + prompt)

约束不靠自觉, 靠两条腿:

1. **设施(机器)**: `omni review submit` 提交某 kind 时, 读该 kind 注册 Format 的 `semantic_preconditions` 回**友情提示**; `content_validators` 按 kind 校验必备件, 缺则进 `structure_warnings`。
2. **prompt(规范/模板)**: 友情提示指向 `docs/standards/review/<类型>规范.md` + `docs/standards/review/templates/<类型>.md`, agent 据此产出。

二者同源、互为指针, 杜绝散落/旁路/重复造轮。

## 已立实例

| 主体类型(kind) | 呈现形态 | 规范 | 立于 |
|---|---|---|---|
| `webgame-spec`(网页交互游戏新建/持续跟进) | 三件套: 引导演示 + 文档 + 文件树 diff | [review/引导演示材料规范.md](../review/引导演示材料规范.md)、[review/spec报告材料规范.md](../review/spec报告材料规范.md) | 2026-06-13(首个) |
| 通用 reviewable(图/文档/网页/关键问题/自定义) | 导览三件套(对应需求/完成度/体验路径) | [review/审阅与推送规范.md](../review/审阅与推送规范.md) | 2026-05-29 |

## 扩展协议(新增主体类型时必走)

新增一种待审阅主体类型, 按序做完四步, 缺一不算立:

1. **立 Format**: 在 `packages/services/_core/omnicompany/formats.py` 注册带 tag `review.kind.<name>` 的 Format, `semantic_preconditions` 写清该类型的呈现形态要求 + 指向规范/模板。
2. **写规范 + 模板**: `docs/standards/review/<name>规范.md` + `docs/standards/review/templates/<name>.md`; 先想清"如何呈现给用户实现最大化信息传递率"。
3. **接设施校验**: 在 `reviewstage/content_validators.py` 加该 kind 的必备件校验分支(仅警告不拒绝)。
4. **登记**: `docs/standards/_meta/standards-index.yaml` 加条目, `context-bindings.yaml` 视情况加 profile。

## 适用 / 谁读

- **任何要新增"待审阅材料主体类型"的 agent / 总控**: 先读本文, 按扩展协议立, 不得绕过设施直接散落新格式。
- 关联: [审阅与推送规范.md](../review/审阅与推送规范.md)、[concepts/material.md](../concepts/material.md)、[_global/standards_meta.md](../_global/standards_meta.md)。
