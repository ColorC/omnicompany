
# dashboard frontend · 测试运行方式

按 [2026-05-09]DASHBOARD-DOGFOOD-RESILIENCE 阶段 10 配套. 三层测试体系:

## 1. vitest 单元测试 (前端 hooks / utils)

跑 hooks / 纯函数级测试, 用 jsdom + mock WebSocket. 不需要真 dashboard / daemon 在跑.

```bash
cd src/omnicompany/dashboard/frontend
npm test              # 单跑全部 unit 测试 (.test.ts / .test.tsx)
npm run test:watch    # watch 模式, 改文件自动重跑
npm run test:coverage # 带覆盖率报告 (要装 @vitest/coverage-v8)
```

当前覆盖:

- `lib/wsAutoReconnect.test.ts` — 6 case (CASE1-6) 验证: 首次 connect / server close 重连 / 退避到 30s 上限 / 待发送队列 / 主动 close 不重连 / longDisconnect → disconnected. 行覆盖率 94%, 分支 86%.

新加 hook / util 时建议直接加 `*.test.ts` 同目录, vitest config (`vitest.config.ts`) 已经配 `src/**/*.test.ts` glob.

## 2. Playwright e2e (浏览器端到端)

真启动 dashboard + ccdaemon 双进程, 真打开浏览器跑 chat session 含 LLM 推理. 单跑 ~45s, 6 spec 跑全套.

跑前提: 本机装 claude binary + 已 `claude login` (Claude Max 订阅).

```bash
cd src/omnicompany/dashboard/frontend
npx playwright test                      # 跑全部 e2e
npx playwright test cc_chat_resilience   # 单跑 chat 韧性 spec (6 个场景)
npx playwright test --headed             # 看浏览器真渲染 (debug 用)
```

`tests/e2e/global-setup.ts` 自动起两进程, `global-teardown.ts` 自杀; 用户已经手动起 dashboard 在 8200 时, globalSetup 会跳过 spawn 不动用户工作环境.

不装 claude binary 时, chat e2e 自动 SKIP (test.skip), 不 FAIL.

## 3. 后端 dogfood + 严密 e2e (Python)

跑 dashboard / ccdaemon 进程级隔离 + 反向代理 + 重连协议:

```bash
cd <repo root>
python scripts/dogfood_dashboard_resilience_test.py    # 6 场景, echo + health, ~30s
python scripts/dogfood_dashboard_strict_test.py        # 12 场景, 真 chat, ~3min
```

严密版会真创 chat session 跑回合, 烧少量 LLM token.

## 三层关系

| 层 | 验证范围 | 时长 | 何时跑 |
|---|---|---|---|
| vitest unit | 前端 hook 状态机器 | < 1s | 改 hook / lib 时 |
| Playwright e2e | 视觉 + 浏览器侧重连协议 | ~1min | 改 frontend / chat UI 时 |
| Python dogfood | 后端进程隔离 + 反向代理 | 3-5min | 改 dashboard / ccdaemon 时 |

跨修改时全跑.

## 后续 (debt)

- CI workflow (GitHub Actions / GitLab CI) 触发: 当前没 CI yaml, e2e + unit 都靠手跑
- vitest 覆盖率门控 (--coverage --reporter=text-summary 强制 ≥ 90%)
