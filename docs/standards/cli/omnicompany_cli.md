
# omnicompany CLI 注册流程规范 (草案)

> **状态**: 草案 (2026-05-01) — 接口契约定下来, 等阶段三实装
> **关联**: `omni-header.md` / `sandbox.md` / `feedback_omnicompany_cli_register_before_write.md`
> **现存基础**: 部分命令已实装 (`omni guardian patrol` / `omni guardian trace` / `omni guardian whitelist` 等), 本规范扩到注册中心层

## 一、 整体设计

omnicompany CLI 是**写入者**跟 omnicompany 系统的官方接口。任何想往 omnicompany 项目目录写东西的角色 (AI IDE / 用户 / 工人 / 外部脚本) 都通过这套 CLI 走注册流程, 拿凭据后才合法写入。

设计上分四组命令:

**身份组** (`omni register identity` / `omni whoami`) — 写入者身份注册和查询。
**材料组** (`omni register material` / `omni register batch`) — 把要写的内容登记到注册中心。
**沙盒组** (`omni sandbox *`) — 草稿区操作, 配合沙盒规范用。
**锁组** (`omni lock *`) — 防修改锁开关和状态。
**守护组** (`omni guardian *`, 已有) — 巡检 / 罚单 / 白名单 / 沙箱违规处理。
**指引组** (`omni guide` / `omni reflect`) — 查规范、用语义反思辅助。

## 二、 身份组

### 2.1 `omni register identity`

注册当前写入者的身份, 拿到一个身份 token, 后续注册操作都带这个 token。

```
omni register identity --session=<session_id> [--role=ai-ide|user|worker]
```

参数:
- `--session=<id>` 必填 — 当前 session 的 ID。AI IDE 调时从 `<workspace>/.omni/sessions/_current.txt` 读; 用户在终端调时, CLI 自己反推或要求显式传。
- `--role=<role>` 可选 — 写入者角色, 默认 `ai-ide`。允许的值: `ai-ide` / `user` / `worker:<class_path>`。

输出:
- 标准输出一个 JSON, 含 `identity_token` (短期 token, 类似 `id-bd9cde92-1ab2c3d4`)、`expires_at` (token 过期时间, 默认 24h)、`role`、`session_id`。

落盘:
- `<workspace>/.omni/identities/<identity_token>.json` 存这条身份记录, 后续注册操作可校验。

### 2.2 `omni whoami`

不注册新身份, 只查当前已注册过的身份。

```
omni whoami [--session=<session_id>]
```

参数:
- `--session=<id>` 可选 — 不传时用当前 session, 传时查指定 session 已注册的身份。

输出: 已注册的 identity_token 列表 (一个 session 可能注册过多个身份, 例如不同 role)。

## 三、 材料组

### 3.1 `omni register material`

单条注册一份要写的内容, 拿写入凭据。

```
omni register material \
    --identity=<identity_token> \
    --kind=<concept_type> \
    --path=<目标路径> \
    [--summary=<内容简洁描述>] \
    [--why=<位置语义理由>] \
    [--tags=<逗号分隔标签>]
```

参数:
- `--identity=<token>` 必填 — 身份注册时拿到的 token。
- `--kind=<type>` 必填 — 概念类型, 取值在八种基础概念里: `material` / `worker` / `team` / `agent` / `hook` / `tool` / `data` / `plan` / `template`。
- `--path=<path>` 必填 — 准备写入的目标路径 (项目相对或绝对)。CLI 验证路径是否在合法目录范围 (按概念类型对应的目录规范)。
- `--summary` / `--why` / `--tags` 可选 — 跟 OmniMark 头三字段对齐, 注册时一起填写。CLI 写入时会自动把这些字段塞进文件头。

校验 (注册中心做):
- 路径是否合法 (在那个 kind 该去的目录里, 不在的话拒)
- 命名是否符合那个 kind 的命名规范 (例如 worker 必须 `<动词>_<名词>_worker.py`)
- 是否跟现有注册项冲突 (不允许同 path 重复注册)
- 是否在锁外的合法路径 (沙盒 / 注册中心数据 / 罚单区) — 这些不该走材料注册

输出: 写入凭据 JSON, 含 `write_credential` token、目标路径校验结果、自动生成的 OmniMark 头模板 (写入者可以直接拿去复制粘贴到文件开头)。

之后写入者用这个 `write_credential` 实际写文件:
- 走 omnicompany CLI 的写入接口 (例如 `omni write --credential=... --content=...`)
- 或者直接 Edit / Write 工具写文件 (但要带凭据 token 在文件头里, 守护扫到没凭据的写入会罚单化)

### 3.2 `omni register batch`

一次批量注册多条内容。用户原话"允许批量注册, 但是写错会有问题" 落到这条命令。

```
omni register batch --identity=<token> --manifest=<清单文件>
```

参数:
- `--manifest=<file>` — 清单文件 (YAML/JSON), 每一条带 `kind` / `path` / `summary` / `why` / `tags` 五字段。

行为 (按用户拍板的"部分失败 + 聚合报告"模式):
- 逐条注册, 错的进罚单区作"非法批量注册"归档 (跟单条注册错的处理一致), 对的进注册中心
- 全跑完后输出聚合报告: `total / success / failed / failure_breakdown_by_reason`

输出: 聚合报告 JSON 落到标准输出 + 详细日志落到 `<workspace>/.omni/registrations/batch-<timestamp>.log`。

## 四、 沙盒组

### 4.1 `omni sandbox open`

返回沙盒目录路径, 不做其他事。

```
omni sandbox open
```

输出: 当前 workspace 的沙盒路径, 例如 `/e/workspace/.omni/sandbox/drafts/`。

### 4.2 `omni sandbox check`

用对应 kind 的规范确认办法自检沙盒里某份内容是否符合规范。

```
omni sandbox check --content=<草稿路径> --kind=<concept_type>
```

行为:
- 读草稿内容
- 按 kind 对应的规范 (在 `<workspace>/.omni/sandbox/guides/<kind>.md` 里) 跑各项检查
- 例如 worker 检查: `FORMAT_IN` / `FORMAT_OUT` 是否声明、`run()` 方法是否存在、是否有跨调用状态、文件头是否带 v3 五字段、命名是否符合规则等

输出: 检查清单结果 JSON, 哪些过哪些没过, 没过的给具体修复建议。

### 4.3 `omni sandbox promote`

把沙盒草稿走注册流程转到正式区。

```
omni sandbox promote --content=<草稿路径> --target=<正式路径>
```

行为:
- 内部走 `omni register material` 把草稿登记
- 校验通过后, 把草稿内容 (附上自动生成的 OmniMark 头) 写入 target
- 注册中心登记这一条
- 沙盒里的草稿可选: 立即删 / 留在 drafts/ 等定期归档

参数:
- `--keep-draft` 可选 — 不立即删草稿, 留在 drafts/ 等归档

### 4.4 `omni sandbox archive`

手动触发沙盒归档 (定期归档由守护进程做)。

```
omni sandbox archive [--keep-days=<天数>]
```

行为:
- 把 `drafts/` 里所有内容打包到 `archive/<YYYY-MM-DD-HHMM>/`
- 清空 `drafts/`
- 归档目录的旧归档按 `--keep-days` (默认 90 天) 清理

### 4.5 `omni sandbox guide`

查某种概念的规范向导 (相当于把对应 guide 文件 cat 出来)。

```
omni sandbox guide --kind=<concept_type>
```

输出: `<workspace>/.omni/sandbox/guides/<kind>.md` 的内容。

## 五、 锁组

### 5.1 `omni lock open`

打开防修改锁, 进入"未注册写入会被罚单化"模式。

```
omni lock open
```

行为:
- 检查注册中心是否就绪 (没有的话拒)
- 检查所有现存内容是否合规 (大量未合规时给警告但不拒)
- 启动守护进程的实时拦截模式
- 写一个 lock 状态文件 `<workspace>/.omni/lock/state.json` 记录开锁时间

### 5.2 `omni lock close`

关闭锁, 进入"自由写入但仍记审计"模式。

```
omni lock close [--reason=<解释>]
```

行为:
- 守护进程切换到只巡检不拦截
- 写关锁原因到 `<workspace>/.omni/lock/state.json`
- 不影响已经罚单化的内容 (那些归档不变)

### 5.3 `omni lock status`

查锁的当前状态 + 罚单情况。

```
omni lock status
```

输出: 当前 open/closed、开/关时间、当前周期内罚单数量、最近 N 个罚单清单。

## 六、 指引组

### 6.1 `omni guide`

跟 `omni sandbox guide` 类似但不限沙盒, 直接展示权威规范。

```
omni guide --kind=<concept_type>
```

输出: 对应权威规范 (`omnicompany/docs/standards/<kind>.md`) 内容。

### 6.2 `omni reflect`

让 AI IDE 通过 LLM 辅助反思"内容是否符合位置"。这条是 LLM-driven 的, 给 AI IDE 自检用。

```
omni reflect --content=<内容路径或 -> --target=<目标路径>
```

行为:
- 读内容 (如果是 `-` 就从 stdin 读)
- 看目标路径所在的目录的 `DESIGN.md` (这个目录是干嘛用的)
- 看目标路径所在的概念类型对应的规范
- 调 LLM (default `qwen-3.6-plus`) 反思: 这份内容放这个位置是不是合适? 字段全不全? 命名 OK 吗? 有没有别的位置更合适?
- 输出反思结论 + 建议

LLM 调用走统一的 LLMClient (符合工人标准 R-04), 留痕到事件总线。

## 七、 数据结构

### 7.1 身份记录 (identity)

`<workspace>/.omni/identities/<identity_token>.json`:

```json
{
  "identity_token": "id-bd9cde92-1ab2c3d4",
  "session_id": "bd9cde92-400f-417e-9e5f-fa4889b3887e",
  "role": "ai-ide",
  "registered_at": "2026-05-01T00:00:00Z",
  "expires_at": "2026-05-02T00:00:00Z"
}
```

### 7.2 注册项 (registration)

`<workspace>/.omni/registrations/<credential>.json`:

```json
{
  "write_credential": "wc-1ab2c3d4-5e6f7a8b",
  "identity_token": "id-bd9cde92-1ab2c3d4",
  "kind": "worker",
  "path": "src/omnicompany/packages/services/foo/workers/bar_worker.py",
  "summary": "...",
  "why": "...",
  "tags": ["foo", "bar"],
  "registered_at": "2026-05-01T00:00:00Z",
  "expires_at": "2026-05-01T01:00:00Z",
  "status": "pending|written|expired"
}
```

### 7.3 锁状态 (lock_state)

`<workspace>/.omni/lock/state.json`:

```json
{
  "state": "open|closed",
  "changed_at": "2026-05-01T00:00:00Z",
  "changed_by": "id-bd9cde92-1ab2c3d4",
  "reason": "...",
  "current_period_violations": 0,
  "current_period_started_at": "2026-05-01T00:00:00Z"
}
```

## 八、 跟现存设施的关系

**跟 OmniMark 关系**: CLI 注册成功后给的 `write_credential` 跟 OmniMark 头里的 `module` 字段对应 — 文件头的 `module` 字段填 credential 让守护回查时能找到注册项。

**跟 sidecar 关系**: 不能写注释的文件 (二进制) 通过 sidecar (`<file>.omni.json`) 关联 credential, sidecar 里的 `written_by` 字段填 credential。

**跟现有 guardian 命令关系**: 现有的 `omni guardian patrol` / `omni guardian trace` / `omni guardian whitelist` 等命令保留, 跟新加的 register/sandbox/lock 组并存。守护规则会扩到检查 `module` (credential) 是否在注册中心存在。

**跟 session 持久化关系**: AI IDE 调 `omni register identity` 时不传 `--session=` 会自动从 `<workspace>/.omni/sessions/_current.txt` 读, 减少手动传参出错。

## 九、 实装顺序建议

阶段三按这个顺序实装, 每个小段都能独立跑通:

第一段, 身份组 (`register identity` + `whoami`) — 最简单, 不依赖其他组件, 让 AI IDE 第一步走通注册。

第二段, 材料组 (`register material` 单条) — 加上路径校验和命名校验, 但不接守护硬拦截 (那是阶段五的事)。

第三段, 沙盒组 — 给 AI IDE 草稿区入口。注意 `sandbox check` 跟材料组的 `register material` 校验逻辑要复用, 不要写两套。

第四段, 锁组 + 跟守护对接 — 这是真正的硬拦截上线, 风险高, 单独一段。

第五段, 指引组 + LLM 辅助反思 — 用户体验加强, 最后做。

批量注册 (`register batch`) 在第二段完成后立刻补上, 因为后续合规化迁移要用到。
