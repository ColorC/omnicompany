<!-- [OMNI] origin=ai-ide domain=omnicompany/standards ts=2026-05-02T05:00:00Z type=doc status=active agent=ai-ide-current -->
<!-- [OMNI] summary="元 IO 规范 - tool 操作绑定状态 + I/O 语义原子化注册, 实施层留下一阶段" -->
<!-- [OMNI] why="用户原始需求 6.6: 所有 I (输入观察) 和 O (输出操作) 要统一注册为元 IO. 这层让 tool 操作可被状态检查/反查根除/锁机制扩展" -->
<!-- [OMNI] tags=cli,meta_io,tool,standard,draft -->
<!-- [OMNI] material_id="material:standards.meta_io.spec.md" -->

# 元 IO 规范 (Meta IO)

> **状态**: 设计草案 (2026-05-02). registry meta_io 类型已加, 实施层骨架留下一阶段
> **关联**: `tool` 概念 (用户原始需求 6.6) + G2 注册中心 + G4 锁组
> **现状**: registry/meta.py 已加 type=meta_io, services/_core/meta_io/ 实施未启动

## 一、 这是干嘛的

用户原始需求 6.6 第 2 点:

> "操作应当和状态绑定, 状态需要可以检查, 所以所有的 I (输入观察) 和 O (输出操作) 都要统一再进行注册, 变为元 IO (语义原子化, 尺寸上可以再分但是语义上不再分的 IO) 再一次进行记录."

含义:

| 概念 | 解释 |
|---|---|
| **I (输入观察)** | tool 读外部状态进入 omnicompany. 例: 读文件 / 查 API / 拉数据库 |
| **O (输出操作)** | tool 改外部状态. 例: 写文件 / 调 API 改远程 / 提交 git |
| **语义原子化** | 这个 IO 不能按语义再分. 尺寸可分 (一行/一段/一字节) 但语义不可分 |
| **元 IO 注册** | 每条原子语义 IO 在 registry 登记, tool 声明它消费 / 产出哪些 meta_io |

这是 **tool 概念深化**. tool 之上还需要更细粒度的"操作 - 状态" 绑定.

## 二、 例子

### 例 1 · 文件读

| Meta IO id | kind | 语义原子 |
|---|---|---|
| `meta_io.fs.read_file_text` | read | 读一份文本文件全文返回 string. 不能再分 |
| `meta_io.fs.read_file_bytes` | read | 读二进制文件返回 bytes. 不能再分 |
| `meta_io.fs.list_directory` | read | 列目录返回名字列表. 不能再分 |
| `meta_io.fs.stat_file` | read | 取文件元数据 (大小/时间). 不能再分 |

**反例** (不是元 IO): `read_csv_file_then_pick_first_row_then_parse` — 这是组合操作, 含 `read_file_text` + `parse_csv` + `pick_row` 三个原子.

### 例 2 · 文件写

| Meta IO id | kind | 语义原子 |
|---|---|---|
| `meta_io.fs.create_file` | write | 创建新文件 (路径不能存在). 不能再分 |
| `meta_io.fs.overwrite_file` | write | 覆盖已有文件全文. 不能再分 |
| `meta_io.fs.append_to_file` | write | 在文件尾追加. 不能再分 |
| `meta_io.fs.delete_file` | write | 删一份文件. 不能再分 |

**注**: `move_file` 是 `read_bytes` + `create_file` + `delete_file` 三个原子的组合, 不是元 IO. 但有时候保留组合 (因为原子化太碎)? 这是 **真原子 vs 工程便利原子** 的张力, 后续设计要拍.

### 例 3 · 网络 / API

| Meta IO id | kind | 语义原子 |
|---|---|---|
| `meta_io.http.get` | read | 单一 HTTP GET, 返回 body. 不能再分 |
| `meta_io.http.post` | write | 单一 HTTP POST, 改远端状态. 不能再分 |
| `meta_io.lark.read_doc` | read | collab platform拉一份文档全文. 不能再分 |
| `meta_io.lark.update_doc` | write | collab platform更新一份文档. 不能再分 |

### 例 4 · git

| Meta IO id | kind | 语义原子 |
|---|---|---|
| `meta_io.git.read_log` | read | 读 git log (含范围). 不能再分 |
| `meta_io.git.read_diff` | read | 读 git diff. 不能再分 |
| `meta_io.git.commit_local` | write | git commit (本地). 不能再分 |
| `meta_io.git.push_remote` | write | git push 到远端. 不能再分 |

## 三、 注册形态

`MetaIO` 实例在 `omnicompany.packages.services._core.meta_io` 下面 (或就近 service 内 `meta_io.py` 文件) 声明:

```python
from omnicompany.packages.services._core.meta_io import MetaIO

META_IO_FS_READ_FILE_TEXT = MetaIO(
    id="meta_io.fs.read_file_text",
    kind="read",
    target_type="file",
    description=(
        "读取一份本地文本文件的全部内容, 按指定编码解码, 返回 str. "
        "前提: 文件存在 + 进程有读权限 + 编码声明跟实际一致."
    ),
    side_effect_scope="local_filesystem.read_only",
    is_atomic_semantic=True,
    state_check=(
        "调用前: 文件路径存在 + 大小 < limit + 编码可识别. "
        "调用后: 进程内存增加 N 字节 / 文件 mtime 不变 / 锁状态不变."
    ),
)
```

TOOL 实施时声明 consumed / produced 元 IO:

```python
class ReadFileTool(BaseTool):
    CONSUMED_META_IO = ["meta_io.fs.read_file_text"]
    PRODUCED_META_IO = []

    def execute(self, args):
        ...
```

注册中心查询:

```bash
omni lookup --kind=meta_io --id=meta_io.fs.read_file_text
omni lookup --kind=tool --consumes=meta_io.fs.read_file_text
```

## 四、 跟 G2 / G4 的联动

### 跟 G2 注册中心

`registry/meta.py` 已加 type=meta_io. 可走 `omni register --kind=meta_io --content=<file>` 显式注册 (但更常见是代码内声明 + AST 扫描型注册, 类似 format/router).

dashboard `/api/v2/registry/instances?kind=meta_io` 可查所有元 IO.

### 跟 G4 锁组扩展

锁的"灵活规则" (用户原话 "什么目录扫 / 什么目录清 / 什么目录追根除") 真正落地需要元 IO:

```json
{
  "watched_paths": [
    {
      "path": "data/_writable/",
      "mode": "evict",
      "watched_meta_io": ["meta_io.fs.create_file", "meta_io.fs.overwrite_file"]
    }
  ]
}
```

意思: 这个目录下只有声明了 `create_file` / `overwrite_file` 元 IO 的 tool 才能写, 其他 tool 直接 evict.

## 五、 状态检查 (state_check)

每个元 IO 必须声明前置状态 + 后置状态:

| 字段 | 含义 |
|---|---|
| `state_check.precondition` | 调用前外部状态必须满足的条件 |
| `state_check.postcondition` | 调用后外部状态预期变化 |
| `state_check.invariant` | 调用前后不变量 (例: 文件 mtime / 锁状态) |

调用前后跑状态检查 hook (PeriodicHook 子类), 不一致就发 `agent.meta_io.violation` event 到 bus.

这是 G4 锁的最深一层 — 不止防"写到错位置", 还防"操作改了不该改的状态".

## 六、 实施层 (留下一阶段)

预留位置: `services/_core/meta_io/`

文件:
- `__init__.py` — 包入口
- `definitions.py` — `MetaIO` dataclass
- `registry.py` — 跟 G2 注册中心联动 (用 `register_type()` 已加 meta_io 类型)
- `state_check.py` — 状态检查 hook (PeriodicHook 子类)
- `audit.py` — 元 IO 调用审计 log

CLI 命令 (留 G2 二期):
- `omni meta-io list` / `omni meta-io describe <id>` — 列 / 看
- `omni meta-io check --tool=<id>` — 检查 tool 的元 IO 声明完整性

## 七、 反模式

**把组合操作当元 IO 注册** — `read_csv_file_then_pick_row` 不是元 IO, 是 `read_file_text` + `parse_csv` + `pick_row` 三个组合.

**tool 不声明 consumed_meta_io** — tool 实施时只放业务代码, 不列消费 / 产出元 IO. 锁机制无法守这个 tool.

**状态检查跑 LLM** — state_check 的 precondition / postcondition 必须是确定性检查 (文件存在 / 大小匹配等), 不能 LLM 判断.

**元 IO id 太粗** — `meta_io.fs.write` 包含 create / overwrite / append / delete 四种语义, 应该拆四份.

**元 IO id 太细** — `meta_io.fs.read_utf8` / `meta_io.fs.read_gbk` 按编码拆是过度. 应该 `meta_io.fs.read_file_text` 一份, 编码当 args.

## 八、 实施引用 (现状 vs 待办)

**已就位**:
- `services/_core/registry/meta.py` 加 `type=meta_io` (本次 session)
- 本规范文档

**待办** (下一阶段):
- `services/_core/meta_io/` 实施层
- `omni meta-io` CLI 命令组
- dashboard `/api/v2/meta_io/*` API
- 现有 SingleToolRouter 子类全部声明 CONSUMED/PRODUCED_META_IO
- G4 锁加 watched_meta_io 规则
