---
omni_project: omni-guard
name: Omni Guard 守护防漂移
group: omnicompany
updated: 2026-06-12
roots:
  - path: /workspace/omnicompany/src/omnicompany/packages/services/_core/guardian
    note: 主目录(规则引擎 + 巡逻 + 罚单处置 + 长驻守护)
  - path: /workspace/omnicompany/src/omnicompany/packages/services/_core/protection
    note: 锁防护(主动防御, omni lock)
  - path: /workspace/omnicompany/.omni
    note: 运行态数据(sentinel 状态/巡逻报告/fix-queue/锁策略)
entry_points:
  - path: /workspace/omnicompany/src/omnicompany/packages/services/_core/guardian/rules
    note: 20 条架构规则(OMNI-001 至 020), 纯计算无副作用
  - path: /workspace/omnicompany/src/omnicompany/packages/services/_core/guardian/sentinel.py
    note: 长驻守护进程(活跃才扫, 冷却节流, pid 单例)
  - path: /workspace/omnicompany/src/omnicompany/cli/commands/guardian.py
    note: omni guardian 全部子命令
  - path: /workspace/omnicompany/src/omnicompany/cli/commands/protection.py
    note: omni lock 全部子命令
  - path: /workspace/omnicompany/docs/standards/cli/omni-header.md
    note: OmniMark 文件身份头规范(权威, v3)
  - path: /workspace/omnicompany/docs/standards/cli/lock.md
    note: 锁防护规范(权威)
latest:
  - "2026-05-02 锁防护离线版完成(enable/scan/handle/baseline 全套), 实时拦截是下一阶段, 规范见 docs/standards/cli/lock.md"
  - "2026-05-01 OmniMark 身份头规范升到 v3, 见 docs/standards/cli/omni-header.md"
  - "2026-04-23 sentinel 最近一次自动巡逻; 巡逻能力本身完整(按 git diff/全量/回溯), 近期以手动 patrol 为主"
quick_actions:
  - label: 巡逻一遍
    skill: null
    where: /workspace/omnicompany
    desc: venv/Scripts/omni.exe guardian patrol (按 git diff 跑 20 条规则, 只警告不改文件; --full 全量)
  - label: 健康检查
    skill: null
    where: /workspace/omnicompany
    desc: venv/Scripts/omni.exe guardian health (完整守护管线, --fix 自动清理根目录违规文件)
  - label: 看罚单
    skill: null
    where: /workspace/omnicompany
    desc: venv/Scripts/omni.exe guardian tickets (违规罚单列表; whitelist/restore 处理)
  - label: 守护报告
    skill: null
    where: /workspace/omnicompany
    desc: venv/Scripts/omni.exe guardian report (聚合规则扫/巡逻/审计成 Markdown 报告)
  - label: 锁状态
    skill: null
    where: /workspace/omnicompany
    desc: venv/Scripts/omni.exe lock status / scan / handle (看锁、离线扫违规、按类处置)
links: []
---
# Omni Guard 守护防漂移

## 概况

omnicompany 的守护设施, 防止仓库被各路 AI 写漂: 20 条架构规则盯着代码不偏离规范,
每个文件带 OmniMark 身份头可溯源(谁写的/什么时候/哪条 trace), 违规生成罚单按来源
自动处置(内部管线的进 fix-queue 等确认, 外部 agent 的警告-隔离-清理三段式),
再加一把"锁"防外部直写关键目录。

## 当前进展

主体能力齐了: 规则引擎 20 条、巡逻(手动 patrol + sentinel 长驻自动)、罚单全生命周期
(生成/白名单/恢复/溯源)、OmniMark 身份头 v3、锁防护离线版(2026-05-02 完成)。
锁的下一阶段是实时拦截(写入前钩子 + 文件监视), 分五级逐步收紧, 还没动工。
两条已知未修违规: creative_content 包未注册到管线注册表、lang_rewrite 有死 Router。
权威规范在 docs/standards/cli/(omni-header.md / lock.md), 计划在 docs/plans/guardian/。

## 主要目录

- guardian/rules: 20 条规则模块, 每条独立检查
- guardian/workers: 巡逻三段链(扫 git diff、跑规则、出罚单)
- guardian/sentinel.py: 长驻守护进程, 看 .omni/core_activity_ts.json 判断有没有新活动
- guardian/tow_truck.py + auto_comment.py: 罚单管理 + 按来源双轨处置
- protection/: 锁防护(策略/扫描/处置)
- .omni/: 运行态(sentinel 状态、最新巡逻报告、fix-queue、锁策略)

## 能做什么

1. 规则巡逻: 按 git diff 或全量扫 20 条架构规则, 只警告不动文件
2. 罚单处置: 违规生成罚单, 按来源自动决策(修复草稿/警告/隔离), 可白名单豁免
3. 身份溯源: 给文件打/查 OmniMark 头, 违规能溯到来源 agent 和 trace
4. 锁防护: 圈定监视目录, 离线扫内部错位和外部直写, 打注释或移出
5. 长驻自动: sentinel 守护进程活跃触发增量扫, 冷却节流
6. 周边工具: 僵尸进程扫描、架构地图校验、Format/Router 描述质量报告

## 常见展开方式

- 例行体检: omni guardian patrol 或 health, 有违规看 tickets 再决定 whitelist/修
- 出守护报告: omni guardian report, 落在 data/services/guardian/reports/
- 查"这文件谁写的": omni guardian who <文件>; 溯源违规用 trace-violation
- 动锁之前先读 docs/standards/cli/lock.md, 历史存量先 baseline 快照再开
- 改规则/加规则: 去 guardian/rules/, 每条规则一个模块
