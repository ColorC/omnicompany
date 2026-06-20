<!-- [OMNI] origin=ai-ide domain=omnicompany/standards ts=2026-05-02T08:00:00Z type=doc status=active agent=ai-ide-current -->
<!-- [OMNI] summary="cc_wrapper hooks 规范 - claude code SessionStart/PreToolUse/PostToolUse/Stop/PreCompact 跟 omnicompany 集成" -->
<!-- [OMNI] why="dashboard cc_wrapper/hooks/ 已实施 6 个 hook (session_start/trace/todos/compact/lock_pretooluse), 散落规范不全. 这份集中规范化让新加 hook 时知道协作模式" -->
<!-- [OMNI] tags=cli,cc_wrapper,hooks,claude-code,standard -->
<!-- [OMNI] material_id="material:standards.cc_wrapper_hooks.spec.md" -->

# cc_wrapper hooks 规范

> **状态**: v1 (2026-05-02), 集中现有 6 个 hook 的规范
> **关联实装**: `dashboard/cc_wrapper/hooks/` 全部 + `services/_core/identity/` + `services/_core/protection/`
> **关联规范**: `identity.md` (G1) / `lock.md` (G4) / `omnicompany_cli.md`

## 一、 这是干嘛的

claude code 启动时 + 调工具时 + 停止时触发本地 hook 命令. cc_wrapper 提供一组 hook 让 claude 跟 omnicompany 设施联动:
- **SessionStart**: 记当前 session 身份到 active 文件 (跟 G1 联动)
- **PreToolUse**: 拦写入工具 (跟 G4 锁联动)
- **PostToolUse**: 落工具调用 trace 到 SQLite event bus (跟 G2 / G4 / dashboard 联动)
- **PreCompact**: 提示用户 / 落审计
- **Stop**: turn 结束信号
- **TodoWrite (PostToolUse)**: 同步 TodoWrite 到 plan.md

## 二、 现有 6 个 hook

| hook 文件 | 触发事件 | matcher | 作用 | 跟设施联动 |
|---|---|---|---|---|
| `session_start.py` | SessionStart | * | 抓 session_id + active_plan, 写 active 文件 + emit `task.intent` event | G1 身份 / `data/cc_session_active.json` |
| `trace.py` | PreToolUse / PostToolUse / Stop | * | 把每个工具调用落 SQLite event bus (`agent.tool.call` / `agent.tool.result` / `task.finish`) | G1 writes 派生 / G4 PreToolUse 联动 |
| `todos.py` | PostToolUse | TodoWrite\|Edit\|Write\|MultiEdit | 同步 TodoWrite 到 plan.md `## Todos` 段 | plan 规范 v1 binding |
| `compact.py` | PreCompact | manual\|auto | 落 compact 审计 + warning | session 持久化 |
| `lock_pretooluse.py` | PreToolUse | Edit\|Write\|MultiEdit\|NotebookEdit | G4 实时拦截 (warn/enforce/off) | G4 锁 / `protection_policy.json` |

## 三、 共用约定

### 1. 短脚本 (sub-100ms 启动)

每 hook 是一个 .py 脚本, 由 `<python> -m <module>` 调用. 启动开销直接影响 claude 工具调用响应时间. 共用:
- 只 import `_shared` + stdlib
- 不 import 重的业务包 (避免 tooling chain 加载)
- 落盘走 SQLite + jsonl, 不走 ORM

### 2. stdin / stdout 协议

- **输入**: claude 把 JSON 写到 hook stdin (含 session_id / tool_name / tool_input / tool_response 等)
- **输出**: hook 把 JSON 写到 stdout (供 claude 解析). 主要 envelope:
  - `additionalContext` — 把内容注入下一轮 LLM context (PreToolUse/SessionStart)
  - `permissionDecision` — `"allow" / "deny" / "ask"` (PreToolUse 用)
  - `systemMessage` — 给用户看的提示 (任何事件)
- **退出码**: `0` = 放行 / `2` = 阻断 / 别的 = error

### 3. 共用 _shared 模块

`hooks/_shared.py` 提供:
- `read_stdin_json()` — 读 stdin JSON (容错)
- `repo_root()` — 找 omnicompany 项目根
- `detect_active_plan()` — 找当前 active plan
- `trace_id_for(payload)` — 派生 trace_id (优先级链: PTY_ID > claude_session_id > unknown)
- `emit_event(...)` — 写 SQLite event bus
- `append_audit(...)` — 写 jsonl 审计

新加 hook 必须走这些, 不另立 db / event 入口.

### 4. trace_id 派生统一

跟 G1 [identity.md](identity.md) 第二节一致. 任何 hook emit 的 event 都用 `trace_id_for(payload)` 派生 trace_id, 让 dashboard / G2 / G4 都看到同一身份.

### 5. 失败容错

hook 失败不阻塞 claude. 任何异常 catch + stderr warn + 返回 0. 例外: `lock_pretooluse.py` enforce 模式才主动 exit 2.

## 四、 加新 hook 流程

1. 在 `hooks/` 加 `<your_hook>.py`, 含 `def main() -> int`
2. import `_shared` 走共用基础
3. 在 `settings_installer._desired_settings_slice()` 加 `_hook_block(...)` 列表项
4. 用户跑 `omni cc install` 同步到 `.claude/settings.json`
5. 测试: 模拟 stdin payload 调 `<python> -m <module>` 看 stdout / exit

## 五、 反模式

**hook 里 import LLMClient / agent loop** — 启动开销大, claude 工具调用变慢. 重业务走 hook 写事件, 别处消费.

**hook 自己派生 trace_id 而不走 `trace_id_for`** — 跟 G1 不一致.

**hook 失败 raise 阻塞 claude** — 必 catch + stderr + 返回 0 (除非 lock enforce 主动阻断).

**hook 直接写 omni-data 文件** — 应当走 SQLite event bus / jsonl audit 入口, 不直接写业务文件 (避开 G4 锁).

**新加 hook 不在 settings_installer 注册** — 用户不会自动看到, 也不能 uninstall.

## 六、 演进 (留下一阶段)

- **hook 也走 ConfigurableXxx 路线** — 现 hook 是 .py main() 函数, 应当跟 ConfigurableEventHook 体系靠拢
- **hook 跟 G2 注册中心联动** — 现 hook 不在 registry, 应当注册 type=hook
- **hook 性能监控** — `_shared.append_audit` 加 elapsed_ms, dashboard 看 hook 慢的统计
- **跨平台 hook** — 现 settings.json 路径 hardcode Windows / Linux 差异, 应当抽离
