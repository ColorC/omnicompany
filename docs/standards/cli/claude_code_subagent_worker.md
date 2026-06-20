<!-- [OMNI] origin=codex domain=omnicompany/standards/cli ts=2026-05-17T00:00:00+08:00 type=standard status=active agent=codex -->
<!-- [OMNI] summary="Codex 通过 omni worker run claude-code 把 Claude Code 作为受控子 worker 的工作边界" -->
<!-- [OMNI] why="用户要求 Codex 主持计划、review、debug、验收和精调，Claude Code 负责长时段代码本体生成；同时要求 skill 放在 omnicompany 内部" -->
<!-- [OMNI] tags=cli,worker,claude-code,codex,spec-driven,review -->
<!-- [OMNI] material_id="material:standards.cli.claude_code_subagent_worker.md" -->

# Claude Code 子 Worker 工作法

本规范只定义 omnicompany 内部协作边界。Codex 负责计划、spec、退出标准、review、debug、验收、必要的高精度修改和清理；Claude Code 通过 `omni worker run claude-code` 负责按 spec 做长时间实现、批量改造或大范围调查。

## 触发条件

使用这个工作法的典型场景：

- 任务需要大量代码生成、迁移、补齐或批量重构，Codex 直接写会占用过多上下文。
- 任务需要先做长时间只读盘点，再由 Codex 决定下一步实现 spec。
- 用户明确要求 Claude Code 作为 Codex 的子 worker。

不适用场景：

- 单文件小改、窄范围 bugfix、简单命令验证。
- 需求边界还没有足够严格，Claude 可能为了满足局部指标而偏离用户原意。
- 需要打印或转交本地密钥、token、plugin secret 等敏感内容。

## 基本命令

从 omnicompany 仓库根目录运行：

```powershell
omni worker providers --json
```

确认存在 `claude-code` 后，用 stdin 传递一次性 spec，避免留下临时文件：

```powershell
@'
# Spec

Goal:
- ...

Scope:
- ...

Non-goals:
- ...

Acceptance:
- ...
'@ | omni worker run claude-code --stdin --cwd . --permission workspace-write --timeout 1800 --json
```

对于需要写入数据目录、计划目录、忽略目录或中文路径的任务，必须显式传 `--watch-path`。`changed_files` 只表示 git status 新增的路径，在脏工作区、已存在脏文件、被 `.gitignore` 忽略的数据根、中文路径写错目录时都可能不足以验收。

推荐形态：

```powershell
@'
# Spec
...
'@ | omni worker run claude-code `
  --stdin `
  --cwd . `
  --run-root D:\P4\main\AIWorkSpace\temp\prefab-workstation-claude-workers `
  --permission workspace-write `
  --timeout 1800 `
  --watch-path data/domains/demogame_ux/ontologies/切磋活动_西瓜杯 `
  --json
```

长跑或批量委托必须显式传 `--run-root`。该目录用于写入 `prompt.md`、`context_*.md`、`request.json`、`result.json`，全部使用 UTF-8 no BOM；Prefab Workstation 相关任务推荐使用 `D:\P4\main\AIWorkSpace\temp\prefab-workstation-claude-workers`，不要把 worker 会话、日志、临时 prompt 放进 `app\tool\prefab-workstation` 包内。CLI 会额外给 worker 注入 `PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`、`OMNI_EXTERNAL_WORKER_RUN_ID` 等环境键，避免每个调用方重复处理 Windows 编码和运行编号。

批量铺量前必须显式指定用户要求的 Claude Code 模型，不依赖账号默认模型。Claude CLI 支持 `--model <model>`，可使用别名或完整模型名；如果用户要求 Opus 4.7，本轮 worker 命令必须显式传入本机 Claude Code 可接受的 Opus 4.7 模型标识，并在 `result.json` 与 DB trace 中复核实际返回模型。不得把一次默认落到其他 Opus/Sonnet 版本的运行说成已经使用 Opus 4.7。

`omni worker run claude-code` 现在有两层审计：

- `--run-root`：落 `prompt.md`、`context_*.md`、`request.json`、`result.json`，保留完整 SDK 事件流，适合事后精查。
- `data/events.db`：外部 worker 运行时镜像关键事件，trace_id 默认为 `run_id`；Claude SDK 的 `tool_use` / `tool_result` 会写成 `agent.tool.call` / `agent.tool.result`，用于快速查看它实际调用了什么工具、传了什么参数和返回了什么。

Dashboard/IDE Claude hook 路径仍写 `data/ide_events.db`。这是另一路会话级观测，不要与 `omni worker run` 的外部 worker trace 混为一谈。

快速查询：

```powershell
omni worker trace external-cli-... --db events --json
```

复核 worker 时优先看 DB trace 的工具调用和 `raw.watched_path_changes`，再看 Claude 的最终文字报告；最终文字报告只能作为摘要，不能作为验收事实。

对于必须阅读的中文路径或长路径上下文，不要要求 Claude Code 自己凭文件名重新定位。Codex 应优先用 `--context-alias alias=path` 把文件内容直接附加给 worker，并在 spec 中只引用 ASCII alias。这样可以减少中文路径被误读、mojibake 化或读到相邻计划文件的风险。

`--context` 和 `--context-alias` 的相对路径按 `--cwd` 解析，不按调用 `omni` 时所在目录解析。跨仓库调度时应把 `--cwd` 设为目标工作区根目录，然后用目标工作区内的相对路径写 alias。

推荐形态：

```powershell
omni worker run claude-code `
  --prompt "Read attached alias gap_doc and summarize only that context." `
  --context-alias gap_doc=docs/plans/demogame/[2026-05-17]UX-PREFAB-WORKSTATION/核心差距与后续Spec补充.md `
  --cwd . `
  --permission readonly `
  --json
```

只读调查必须使用 `--permission readonly`。实现型任务通常使用 `--permission workspace-write`。`trusted-bypass` 只能在用户明确批准后使用，并且必须传 `--allow-trusted-bypass`。

不推荐用 PowerShell `Start-Process` 后台启动 Claude Code worker。实测 SDK 通道可能出现进程仍在但 stdout/stderr 长时间为空的状态，Codex 会失去有效进度观测。长任务优先使用前台 `omni worker run ... --json`，或由上层已经支持事件流和超时的调度器托管；如果确实需要后台运行，必须另做心跳、stdout/stderr、目标 watch path 和超时收束。

## Codex 必须写进 Spec 的内容

每次交给 Claude Code 前，Codex 必须把以下内容写清楚：

- 目标：本轮要完成什么用户可感知结果。
- 忠实度：原始需求中哪些语义不能被替换成指标。
- 文件边界：允许读哪些路径，允许改哪些路径，禁止改哪些路径。
- 非目标：本轮不做什么，尤其是不做自我安慰式报告页、无关重构、临时产物堆积。
- 输入证据：需要读取的计划、代码、数据、截图、文档、运行结果。
- 中文路径上下文：关键中文路径内容必须通过 `--context-alias` 附带，并在正文里只引用 ASCII alias；不要让 Claude Code 自己猜中文文件名。
- 退出标准：必须是客观可复核的文件、UI、测试或命令结果，而不是“覆盖率看起来足够”。
- 清理要求：不能留下临时 spec、缓存、会话文件；必须报告 `changed_files` 和跳过的检查。
- 审计路径：对所有允许写入目录都传 `--watch-path`，尤其是 `data/domains/demogame_ux/`、`docs/plans/.../state`、`.omni` 以外的临时 evidence 目录和任何中文路径。

## Codex 的复核责任

Claude Code 返回后，Codex 必须先看 JSON 字段：

- `status`
- `final_text`
- `changed_files`
- `diff_summary`
- `error`
- `raw.watch_paths`
- `raw.watched_path_changes`

若 Claude SDK 的底层 `result` 事件包含 `is_error=true`、`subtype=error/failed/failure` 或 API Error 文本，`omni worker` 必须把本次 run 归一化为 `status=failed`。这类输出不能被解释成 “Claude 已完成但回答里提到一个错误”；它表示 worker 没有产生可信结果，Codex 只能把它当失败处理并决定是否重试、降级或本地接手。

随后执行：

```powershell
git status --short
git diff -- <changed paths>
```

再检查 watch path 审计：

- 如果 `raw.watched_path_changes.has_changes=true` 但 `changed_files=[]`，不能认为 worker 没有写文件；这通常表示写入了 ignored 数据根或 preexisting dirty 区域。
- 如果出现业务名相似但带 `�`、问号、mojibake 或编码异常的目录，必须移动/重做到正确目录并删除错误目录；不能把错误目录保留为“临时产物”。
- 如果 `raw.watched_path_changes` 为空而本轮本应写文件，说明 Codex 没有设置 watch path，本轮验收不完整，必须补跑审计或人工核验目标目录。

再运行最小相关验证。对于前端或工作站 UI，必须尽量打开本地页面做真实交互或截图验证；对于 CLI/数据管线，必须跑对应的真实命令或最小样例。

Codex 可以精调 Claude 的代码，但不能把 Claude 的输出当作已验收结果直接交付。

## Prefab 工作站特别边界

针对 `UX-PREFAB-WORKSTATION` 这类任务，第一次启动 Claude Code 不应直接让它写功能代码。首轮应为只读调查，要求它核对：

- 三份计划与原始需求的矛盾点。
- 旧 `unity-prefab-management`、新 `prefab-workstation`、`wiki-viewer`、`unity-cli-status` 的真实结构和可复用点。
- `data/domains/demogame_ux/` 与 `src/omnicompany/packages/domains/demogame/ux/tools/` 中已有资产和工具，避免重造。
- Feishu 计划文档、Figma 高清图、Prefab 解析、Lua View/Config、Unity 预览之间的真实可达链路。
- 哪些补完计划 P0 项可以作为第一轮 `workspace-write` spec，哪些还缺证据。

只有当只读调查确认输入资产和验证命令可达后，才进入实现型 worker。
