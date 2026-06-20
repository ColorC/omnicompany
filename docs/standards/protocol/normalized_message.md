
# NormalizedMessage 协议规范

供 [`MULTIPROVIDER-CHAT-PLATFORM`](../../plans/dashboard/[2026-05-10]MULTIPROVIDER-CHAT-PLATFORM/plan.md)
阶段 1 立, 后续接入新 provider 实现者参考.

## 1 · 设计原则

1. **后端转, 前端通用消费**: 各 provider 子类 (`ClaudeProvider` / 后续 `CodexProvider` 等)
   在 backend 把自家 SDK 原始消息转换为 NormalizedMessage. 前端 [`ChatInterface`](../../../src/omnicompany/dashboard/frontend/src/components/cc/view/ChatInterface.tsx)
   只识别 NormalizedMessage, **不识别**任何 LLM SDK 形态.

2. **kind 字段是判别式**: 全部用 `kind` 字段区分类型 (TS Discriminated Union 形态).
   legacy 消息 (`type: 'websocket-reconnected'` 等) 不属于本协议, 由其他通道传递.

3. **schema 反推自前端 hook**: kind 名跟字段从 [`useChatRealtimeHandlers.ts`](../../../src/omnicompany/dashboard/frontend/src/components/cc/hooks/useChatRealtimeHandlers.ts)
   的真消费实现反向推导. 加新 kind / 改字段必先改前端 hook + 本规范, 再加 backend 实现.

4. **camelCase 字段命名**: `sessionId` / `requestId` / `toolName` 等. 跟前端 TS 形态对齐, 避免
   ws bridge 时再做命名转换.

## 2 · 通用字段

所有 NormalizedMessage 都可带:

| 字段 | 类型 | 必选 | 含义 |
|---|---|---|---|
| `kind` | string (enum) | **是** | 消息类型判别式, 见下表 |
| `sessionId` | string \| null | 否 | 所属 session ID. 大部分消息选填 |
| `provider` | string | 否 | 来源 provider (例 'claude' / 'codex'), 跨 provider session 区分用 |

## 3 · kind 全集 (14 项)

### 3.1 流式输出

| kind | 字段 | 含义 |
|---|---|---|
| `stream_delta` | `content: str` (必), `sessionId?` | LLM 边生成边推, 前端 buffer 攒成完整段 |
| `stream_end` | `sessionId?` | 当前流式段结束, 前端从 buffer flush 到 store |

### 3.2 session 生命周期

| kind | 字段 | 含义 |
|---|---|---|
| `session_created` | `newSessionId: str` (必), `sessionId?` | provider 创了 session (例 Claude SDK 第一次调用返 session_id), 前端从临时 ID 切到真 ID |
| `complete` | `sessionId` (必), `aborted?: bool`, `actualSessionId?: str`, `exitCode?: int` | 一个 turn 结束 (LLM 答完 + 工具执行完). aborted=true 表示用户中断. actualSessionId 表示后端最终 session ID 跟前端持有的不一致时纠正用 |
| `error` | `error?: str`, `sessionId?` | provider 抛错 / session 异常 / 工具调用上报 |

### 3.3 内容块 (非流式 / 思考 / 工具)

| kind | 字段 | 含义 |
|---|---|---|
| `text` | `content: str` (必), `sessionId?` | 完整文本块, 前端写入 store |
| `thinking` | `content: str` (必), `sessionId?` | 扩展思考块 (Claude thinking content / Codex reasoning) |
| `tool_use` | `toolId: str`, `toolName: str`, `input: dict`, `sessionId?` | LLM 决定调某工具 |
| `tool_result` | `toolId: str`, `result?: any`, `isError?: bool`, `exitCode?: int`, `resultText?: str`, `sessionId?` | 工具执行返回 |

### 3.4 权限交互

| kind | 字段 | 含义 |
|---|---|---|
| `permission_request` | `requestId: str` (必), `toolName: str`, `input?`, `context?`, `sessionId?` | 工具调用待批 (例 Bash exec 命令需用户允许). 前端展示横幅, 等用户 grant |
| `permission_cancelled` | `requestId: str` (必) | 用户取消待批 / 后端 timeout 取消, 前端清横幅 |

### 3.5 状态推送

| kind | 字段 | 含义 |
|---|---|---|
| `status` | `text: str` (必), `tokens?: int`, `canInterrupt?: bool`, `tokenBudget?: dict` | 运行时状态 (例 thinking 中 / 工具执行中). 特殊值 text='token_budget' + tokenBudget=<dict> 时, 前端只更 tokenBudget 不更 status 文字 |

### 3.6 交互场景

| kind | 字段 | 含义 |
|---|---|---|
| `interactive_prompt` | `sessionId?` | LLM 反问用户. 前端默认路由到 store, 无特殊 UI 副作用 |
| `task_notification` | `sessionId?` | 跨 session 异步通知 (例 长跑任务完成提醒) |

## 4 · 不属于本协议的 (legacy)

useChatRealtimeHandlers.ts 同时也处理几类**没有** `kind` 字段的消息, 用 `type` 字段判别.
这些**不属于** NormalizedMessage, 由其他通道传递 (前端 hook 单独处理):

- `type: 'websocket-reconnected'` — wsAutoReconnect 触发的重连通知
- `type: 'pending-permissions-response'` — 后端响应前端"列待批权限"请求
- `type: 'session-status'` — 跨 session 状态轮询 (例 isProcessing 标记)

provider 实现**不应**输出这些 legacy 类型. 以上由 omnicompany 自家 ws 通道 / proxy 层处理.

## 5 · 字段命名约定

- camelCase: `sessionId` / `requestId` / `toolName` / `newSessionId` / `actualSessionId` /
  `exitCode` / `tokenBudget` / `canInterrupt` / `tokenBudget` / `resultText` / `toolId` /
  `isError`
- 通用字段: `kind` (必填) / `sessionId` (大部分选填) / `provider` (选填)
- 不用 `tool_use_id` / `tool_call_id` 这种 SDK-specific 命名 — 协议层统一 `toolId`

## 6 · 协议演进规则

1. **加新 kind**: 必先改 [`useChatRealtimeHandlers.ts`](../../../src/omnicompany/dashboard/frontend/src/components/cc/hooks/useChatRealtimeHandlers.ts) +
   [`normalized_protocol.py`](../../../src/omnicompany/dashboard/ccdaemon/normalized_protocol.py) +
   本规范, 三处同步. 单边加协议字段会导致前后端 drift.

2. **provider 不允许定义专属 kind**: 如果有 SDK 特殊事件, 必须先抽象到本协议中通用 kind,
   然后所有 provider 都遵守. 例如 Claude thinking 跟 Codex reasoning 都对应 `kind: 'thinking'`.

3. **字段加可选优先**: 新加字段默认可选 (`?`), 旧 provider 实现不需要更新; 必填字段加之
   前必先所有 provider 都准备好.

4. **协议版本不打 version 号**: 走"必须前后端同步"约束, 不靠版本号兼容旧版. 单 git
   仓库内部协议简化处理, 不模拟 RFC.

## 7 · 实现参考

- Python TypedDict 定义: [`ccdaemon/normalized_protocol.py`](../../../src/omnicompany/dashboard/ccdaemon/normalized_protocol.py)
- BaseProvider ABC: [`ccdaemon/providers/base.py`](../../../src/omnicompany/dashboard/ccdaemon/providers/base.py)
- 前端真消费 hook: [`useChatRealtimeHandlers.ts`](../../../src/omnicompany/dashboard/frontend/src/components/cc/hooks/useChatRealtimeHandlers.ts)
- 阶段 2 ClaudeProvider 实现 (待写): `ccdaemon/providers/claude.py` — 把 claude-agent-sdk 原始
  message 转 NormalizedMessage 的标杆实现, 后续 provider 子类参考它

## 8 · 阶段对应

| plan 阶段 | 协议相关产出 |
|---|---|
| 阶段 1 (本规范立) | 协议 schema + BaseProvider ABC + 文档 (本文件) |
| 阶段 2 | ClaudeProvider 实现 `claude_to_normalized` 真转换 |
| 阶段 4 | 前端 ChatInterface 接入, NormalizedMessage 真路通 |
| 阶段 6 | CodexProvider / OpenCodeProvider / CursorProvider stub 各自 `*_to_normalized` |
| 阶段 7+ | 各 provider 真接入, 协议演进按本文 §6 规则做 |
