
# Changelog

## [0.2.0] - 2026-06-19

基于 2026-05-24 至 2026-06-19 的非 merge Git 历史整理。
本段是面向人的摘要，不展开完整 commit 列表。

### feat

- Packaging/productization 将核心治理 catalogue 从 FastAPI 边界抽到共享 core 模块，供 dashboard、governance、registry 复用；同时补齐 project URLs、classifiers、README 等打包元信息，并移除误导性的全环境 pip-freeze 锁 (`56f3fd45`)。
- Dashboard/cockpit 产品面持续成熟：统一 shell/UI、项目即首页、对话/计划/审阅材料三列首页、计划审计路由、项目详情一键打开、热更新链路、自管 multi-agent 会话可视化 (`90dad20d`, `2b640a53`, `eeadc7ad`, `784987dc`, `9fe1391f`, `4c4299cc`, `d20f4b9e`)。
- 治理部门成为一等运行层：计划治理、历史挖掘、重复需求归属、benchmark 金标签、可定时治理管线、性价比提交 steward、项目卫生扫描、guardian/sentinel 台账 (`31753444`, `bc240633`, `6cfa4bfb`, `ea1674b8`, `f5919560`, `b124fcf5`)。
- LLM 与 agent 执行面收敛到统一单次/批量调用、确定性 multi-agent workflow、既有会话采纳/resume、progress timeline 和 `/goal` 持续目标循环 (`3fac5241`, `751b2c68`, `00bc0e72`, `f0cbc8b6`, `c584a151`, `f94a86b1`, `751360be`)。
- 对外发布与作品集链路加入人工审批闸、works section 发布、验证钩子、隐私发布脚本；后续也回退了误建在 `aios-flow` 的 portfolio 管线，回到真实 personal-homepage 路径 (`5d89a7d9`, `98542c8d`, `42170613`, `67f89000`, `25565efa`)。
- 材料与审阅流扩展为公司级 Format material、review-stage 接线、authored note 标题、draft rename，以及生产可见的审阅材料聚合 (`1ab0121a`, `9d4551a4`, `50ec28e9`, `49236288`, `b95b67d4`)。

### fix

- Dashboard/cockpit 可靠性修复覆盖缺失产物自愈页、思考/effort 路由、项目工作板权威、扩展重载恢复、loading 状态硬化、用量/429 回退等 (`c3977b6b`, `0cfbceff`, `4ad97365`, `9d612a14`, `8f6df47f`, `affa9154`, `751b2c68`, `4bdc9e6e`, `f3d9064d`)。
- Boss Sight 与 review-stage 修复了递归 spawn 安全洞、审阅裁决误唤起总控、材料 Format 生产可见性、旧权威/死代码残留等问题 (`3a1efd45`, `713d8bc4`, `22d30191`, `50ec28e9`)。
- personal-site 与简历管线修正了发布路径、内容真实性和项目归属，反复对照真实源码/设计文档收敛简历产物 (`44608799`, `123936ce`, `b449d7c3`)。

### refactor

- 配置从全局硬编码路径转向环境变量驱动，提升可移植性；本次没有包名重命名，也没有改业务结构 (`20d09c01`)。
- Agent/event 内部收敛到 EventBus、外部 worker trace、退役 V1 agent loop，并统一 workflow/event 权威 (`58f14a00`, `e6fb4581`, `fedf4108`)。
- Boss Sight 去重确立 workspace root、model resolver、plan frontmatter 等单一权威，同时清理孤儿前端代码和残留类型名 (`36271206`, `91c35317`, `3ed15800`, `d32f8a6d`, `ebd3d872`)。
- Chat/daemon 重建为上游 NormalizedMessage wire、共享库和直接 ccdaemon/main/lifecycle 路径 (`6e99fb71`, `97461c61`, `20c5a504`, `4a0c916e`)。

### docs

- 产品化与发布纪律文档补齐 project、长跑 GOAL、沙盒、可移植性、作品集/dev-log 发布和验收边界 (`44feadb9`, `3bc2ed14`, `bfeba7d7`, `8f4d0c51`, `b3b336a7`, `a4c185ee`)。
- 治理与标准文档合并整理，包括唯一规范体系、agent prompt 反模式、集成测试指南、BOSS Sight 升级/用户故事、总控项目入口说明 (`01710614`, `bc109fe2`, `459b9491`, `206d989f`, `c3dfb489`, `ac1c4973`)。
- 计划文档扩展 dashboard/cockpit 重建、原生 Claude/Codex 会话控制、Figma-HTML 双向同步、作品集发布和 agent-framework 任务交接 (`68b1f2dc`, `fd770a3c`, `f47ae279`, `9e788cfa`, `5ca53a1d`, `bd374e3d`)。

### chore

- 仓库卫生清理了运行/测试残留、pytest 收集污染、guardian 隔离区跟踪、自动台账和旧前端静态 bundle (`82c9c292`, `c4d43998`, `ec90593f`, `38596c50`, `a08a2f94`)。
- job_apply/resume stewarding 与核心包代码隔离，工具迁移到 scripts，并保留个人/隐私数据边界 (`b089ddfd`, `bbd09c2c`, `ecce9d1c`, `24b927e5`)。

### notes

- 本 changelog 不代表 Git 分支合并、release tag、包名重命名、业务逻辑重写或 `src` 结构调整。
- 当前代码中的仓库/包身份仍是 `omnicompany`；未来如有 `omnicompany` 命名工作，按命名债处理，本次不应用到代码。
