# OmniCompany SDK 契约文档

## 核心架构: LAP (Language Anchoring Protocol)

OmniCompany 是基于 **LAP 语言锚定协议** 的多工作流自进化框架。核心层提供声明式管线引擎，各业务组群以 SDK 方式接入。

---

## 层级架构

```
┌─────────────────────────────────────────────────┐
│  组群层 (Groups)                                  │
│  benchmark/ | devlearn/ | unity_explore/ | ...   │
│  各自实现 Router/Transformer, 各跑各的进程         │
├─────────────────────────────────────────────────┤
│  运行时层 (runtime/)                              │
│  PipelineRunner · Router(ABC) · ToolExecutor     │
│  读取 PipelineSpec + 绑定 Router → 驱动执行        │
├─────────────────────────────────────────────────┤
│  协议层 (protocol/)                     🔒 稳定   │
│  PipelineSpec · AnchorSpec · TransformerSpec     │
│  Format · FormatRegistry · FactoryEvent         │
│  Verdict · Route · ValidatorSpec                │
├─────────────────────────────────────────────────┤
│  总线层 (bus/)                          🔒 稳定   │
│  EventBus(ABC) · SQLiteBus · (未来 RedisBus)     │
└─────────────────────────────────────────────────┘
```

**🔒 稳定层** = `protocol/` + `bus/`，任何修改必须更新 `_core_version.py` 版本号。

---

## 核心版本契约

```python
# _core_version.py
CORE_VERSION = "0.2.0"  # 语义化版本
```

### 版本规则

| 变更类型 | 版本变化 | 示例 |
|---------|---------|------|
| 破坏性变更 (删除/重命名公开 API) | MAJOR +1 | 0.2.0 → 1.0.0 |
| 兼容性扩展 (新增字段/方法) | MINOR +1 | 0.2.0 → 0.3.0 |
| Bug 修复 (行为不变) | PATCH +1 | 0.2.0 → 0.2.1 |

### 兼容性检查

```bash
python scripts/check_core_compat.py
```

---

## 组群开发约定

### 目录结构

每个组群是 `src/omnicompany/` 下的一个 Python 子包：

```
src/omnicompany/
├── protocol/         # 🔒 核心协议 (不允许组群直接修改)
├── bus/              # 🔒 事件总线 (不允许组群直接修改)
├── runtime/          # 🔒 运行时引擎 (不允许组群直接修改)
├── _core_version.py  # 核心版本声明
│
├── benchmark/        # 组群: gameplay_system-benchmark ← 模板
│   ├── manifest.py   # 组群声明 (必须)
│   ├── _platform.py
│   ├── flows/
│   └── ...
│
└── <your_group>/     # 新组群
    ├── manifest.py   # 照 benchmark/manifest.py 模板创建
    └── ...
```

### manifest.py 规范

每个组群 **必须** 包含 `manifest.py`，声明：

```python
GROUP_ID = "your-group-id"        # 唯一标识
CORE_VERSION_MIN = "0.2.0"        # 最低兼容核心版本

CUSTOM_FORMATS = [...]            # 本组群扩展的 Format 类型

def register_formats(registry):   # 注册到全局 FormatRegistry
    ...
```

### 多进程隔离模型

各组群独立进程 + 独立 SQLite 数据库：

```python
# 组群 A 的进程
async with SQLiteBus("data/group_a.db") as bus:
    runner = PipelineRunner(my_pipeline, my_bindings, bus)
    await runner.run(input_data)

# 组群 B 的进程 — 完全独立
async with SQLiteBus("data/group_b.db") as bus:
    runner = PipelineRunner(other_pipeline, other_bindings, bus)
    await runner.run(input_data)
```

---

## 公开 API 清单 (v0.2.0)

### protocol/ — 25 个公开符号

| 模块 | 符号 |
|------|------|
| events | `FactoryEvent`, `EventMetadata`, `EventType` |
| format | `Format`, `FormatRegistry`, `ConnectionCheck`, `create_builtin_registry` |
| anchor | `Verdict`, `VerdictKind`, `Route`, `RouteAction`, `ValidatorSpec`, `ValidatorKind`, `Validator`, `AnchorSpec`, `TransformerSpec`, `TransformMethod`, `Transformer` |
| pipeline | `PipelineSpec`, `PipelineNode`, `PipelineEdge`, `NodeKind`, `PipelineChecker`, `PipelineCheckResult`, `EdgeCheckResult` |

### runtime/ — 运行时绑定

| 类 | 用途 | 组群需关注 |
|----|------|-----------|
| `Router(ABC)` | 节点执行接口 | ✅ 组群实现此接口 |
| `PipelineRunner` | 管线执行器 | ✅ 组群用此驱动管线 |
| `ToolExecutor` | 工具执行 | 可选复用 |
| `LLMClient` | LLM 调用 | 可选复用 |

### bus/ — 事件总线

| 类 | 用途 |
|----|------|
| `EventBus(ABC)` | 总线抽象接口 |
| `SQLiteBus` | SQLite 实现 (默认) |

---

## 核心修改警告流程

当需要修改 `protocol/`、`bus/`、`runtime/` 时：

1. **评估影响**: 是 MAJOR/MINOR/PATCH？
2. **更新版本号**: 修改 `_core_version.py` 中的 `CORE_VERSION`
3. **运行兼容性检查**: `python scripts/check_core_compat.py`
4. **通知所有组群**: commit message 标注 `[CORE]` 前缀
5. **各组群更新**: 根据需要更新 `CORE_VERSION_MIN` 并适配
