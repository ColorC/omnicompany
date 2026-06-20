<!-- [OMNI] origin=claude-code domain=docs/standards ts=2026-05-02T00:00:00Z type=standard status=active -->
<!-- [OMNI] material_id="material:standards.global.wysiwyg_drag_drop_coordinate_invariant.md" -->

# 玩家视角拖拽不变量铁律 · WYSIWYG Drag-Drop

> **立档时间**: 2026-05-02 · 由 autochess demo board 用 array 索引锚位实战踩出
>
> **适用范围**: 凡有"玩家拖拽 / 点击 / 操作位置 → 数据状态变更" 的场景, 数据状态必须直接锚到玩家可见的位置坐标, 不允许转译成数组索引或其他间接锚.
>
> **配套铁律**: `cross-end-board-consistency.md`, `test-pyramid.md`.

---

## 一 · 问题来源 (实测漏洞)

2026-05-01 autochess demo 用户实测: 把棋子拖到 hex(col=-12, row=-13), unit 真出现在 board[0] 对应 slotId=1 的 hex (跟玩家拖的位置完全不同). 现状代码:

```js
// state.board: Array(8).fill(null)        ← 锚 array 索引, 不锚 hex
// drop handler:
const slotIdx = board.findIndex(s => s == null);  // ← 找第一个空 slot
store.actions.UNIT_PLACE(unitId, slotIdx, 0);     // ← 不管玩家拖到哪
```

修补丁的尝试 (`slotIdx = (targetCell.slotId || 1) - 1`) 仍是补丁: slotId 1-8 才能映射到 board[0..7], slotId 9-13 截断. 玩家拖到 hex(-12,-13) 还是错位.

**根因**: 数据模型选错锚点. board 用 `Array<unit>` 时, 数组索引跟玩家可见 hex 没绑死, drop handler 写起来想怎么绑就怎么绑. 玩家视角"拖到哪 = 出现在哪" 没被显式表达成数据约束, 只在 spec 散文里写"应该所见即所得", 软 prompt 不可靠.

---

## 二 · 铁律 · 数据状态锚到玩家可见坐标

### 定义

任何"玩家操作位置 → 数据状态变更" 场景, 数据状态的**主键 (key)** 必须是**玩家可见的位置坐标**, 不允许是 array index / slotId / 其他间接 ID.

### 硬规则

1. **状态主键 = 视觉坐标** — 棋盘场景: `Map<HexKey, Unit>` 主键是 `"col,row"` 字符串. 时间轴场景: `Map<TimeStamp, Event>`. 拖拽列表场景: 主键带视觉位置 metadata, 不能仅靠 array index.

2. **action 入参锁视觉坐标** — `UNIT_PLACE(unitId, hexKey)` 不允许 `UNIT_PLACE(unitId, arrayIndex)`. 接口签名硬约束, 即使内部存储用 array 也要在 action 边界转成视觉坐标.

3. **drop handler 不算几何二次** — drop 触发时, drop 派发器 (例 `shared-board drag.js`) 已经把玩家拖到的 px 反推成 `hexKey`, 上层 handler 直接拿 hexKey 用, 不再自己 `findIndex(空 slot)` 或 `picker.find(closest hex)`.

4. **render 用主键反查** — 渲染棋子时遍历 `board.entries()`, 每个 unit 用自己的 hexKey 找对应 hex 锚, **不**用 array index 找第 N 个 hex 槽.

5. **重叠 / 越界严锚** — `board.set(hexKey, unit)` 前必须检查 `board.has(hexKey) === false` (重叠拒) 和 cellmap 该 hex 是 self side (越界拒). 检查在 action 层做, 不在 drop handler 做 (单一拒绝点).

### 玩家视角不变量 (可执行验证)

| 不变量 | 红期注入 (应失败) | 绿期 (应通过) |
|---|---|---|
| I-1 拖到哪 = 出现在哪 | drop 后 unit.position ≠ targetHexKey | unit.position === targetHexKey |
| I-2 重叠拒 | 同 hex 拖第 2 个 unit, board.size 增加 | board.size 不变, 第 2 次 drop 被 reject |
| I-3 越界拒 | 拖到 oppo side / banned hex, board.size 增加 | board.size 不变, drop 被 reject |
| I-4 移动保位 | board → board 移动, unit.position 跟新 hex 同步 | render 渲染到新 hex 不是旧 hex |

### 反模式

- **array.findIndex 找空槽** — 玩家拖到 A 但 unit 出现在第 1 个空槽
- **slotId-1 当 array index** — slotId > 8 时截断, 棋盘大就不能用
- **drop handler 自己算 px → hex** — 三端各自算各自的, 不一致
- **render 用 board[i] 锚到 cellmap[i]** — array 顺序变了棋盘乱了

---

## 三 · 实现 (本次 autochess demo 落地)

### 数据模型

```js
// autochess src/store/types.js (新建)
export type HexKey = string;  // 格式 `${col},${row}`, 例 "0,0" / "-12,-13"
export const HEX_KEY_PATTERN = /^-?\d+,-?\d+$/;
export function hexKey(col, row) { return `${col},${row}`; }
export function parseHexKey(key) {
  const [c, r] = key.split(',').map(Number);
  return { col: c, row: r };
}

// 状态形状
type BoardState = Map<HexKey, Unit>;       // 主键 = HexKey, 不是 Array index
type Unit = {
  id, name, race, stars, hp, attack,
  position: HexKey,                        // 锚到视觉坐标
};
```

### Store actions 锁签名

```js
// autochess src/store/gameStore.js (重构)
actions.UNIT_PLACE(unitId, toHexKey, fromBenchIndex?) {
  // I-1: cellmap 必须存在该 hex
  // I-3: cellmap 该 hex 必须是 self side
  // I-2: board 不许已占
  if (!cellmap.has(toHexKey)) throw new Error(`Invalid hex: ${toHexKey}`);
  const cell = cellmap.get(toHexKey);
  if (cell.side !== 'self') throw new Error(`Not self side: ${toHexKey}`);
  if (board.has(toHexKey)) throw new Error(`Hex occupied: ${toHexKey}`);
  // ... 真置入
  board.set(toHexKey, { ...unit, position: toHexKey });
}

actions.UNIT_MOVE(fromHexKey, toHexKey) {
  if (!board.has(fromHexKey)) throw new Error(`No unit at: ${fromHexKey}`);
  if (board.has(toHexKey)) throw new Error(`Target occupied: ${toHexKey}`);
  const unit = board.get(fromHexKey);
  board.delete(fromHexKey);
  board.set(toHexKey, { ...unit, position: toHexKey });
}

actions.UNIT_REMOVE(hexKey) {
  if (!board.has(hexKey)) throw new Error(`No unit at: ${hexKey}`);
  board.delete(hexKey);
}
```

### Drop handler 简化 (不算几何)

```js
// autochess src/screens/MainBoardPrepare.js (重构后)
function onCellDrop({ source, unitId, fromHexKey, toHexKey, cellEntry }) {
  // shared-board 已经把玩家 px 反推成 toHexKey, 不需要再算
  if (source === 'bench') {
    store.actions.UNIT_PLACE(unitId, toHexKey);
  } else if (source === 'board') {
    store.actions.UNIT_MOVE(fromHexKey, toHexKey);
  }
  // 不变量 I-2/I-3 由 action 内部 throw, drop handler 不重复检查
}
```

### Render 反查

```js
// shared-board src/overlay.js
function renderUnits(svg, units, cellmap) {
  units.forEach((unit, hexKey) => {
    const cell = cellmap.get(hexKey);  // ← 用 hexKey 反查, 不用 index
    if (!cell) return;  // 防御: 数据错乱时不崩
    const { x, y } = hexPos(cell.col, cell.row);
    // ... 渲染 unit overlay 到 (x, y)
  });
}
```

### CI Gate

| Gate | 抓什么 |
|---|---|
| 类型校验 | `BoardState` 必须是 `Map<HexKey, Unit>` 类型, 不能是 `Array<Unit>` |
| 禁字段使用 (ESLint) | drop handler 文件不许出现 `findIndex` / `slotIdx` 这种间接锚 |
| 状态机覆盖 | 每条玩家视角不变量 (I-1 ~ I-4) 至少 1 个状态转移测 |
| 红绿对照 | 测试经红期 (注入 bug 应 fail) + 绿期 (修复应 pass) |

---

## 四 · 反例

### 反例 1 · array.findIndex 找空槽

```js
// 错: drop handler 不管玩家拖到哪
const slotIdx = board.findIndex(s => s == null);
store.actions.UNIT_PLACE(unitId, slotIdx, 0);
```

**修法**: drop handler 拿 toHexKey, 调 `UNIT_PLACE(unitId, toHexKey)`, board 是 Map.

### 反例 2 · slotId-1 当 array index (我之前的补丁)

```js
// 半错: slotId 1-8 时映射对, 9-13 截断
const slotIdx = Math.min(Math.max((targetCell.slotId || 1) - 1, 0), 7);
```

**修法**: 删 slotIdx 概念, 直接用 hexKey 当主键.

### 反例 3 · drop handler 自己算 px → hex

```js
// 错: 三端各自算各自的, 不一致, autochess 算错
const targetCell = cellmap.tiles.find(t =>
  Math.abs(t.col - dropX) < 1 && Math.abs(t.row - dropY) < 1
);
```

**修法**: shared-board drag.js 派出已经反推好的 hexKey, 上层 handler 直接接.

### 反例 4 · render 用 board[i] 锚 cellmap[i]

```js
// 错: array 顺序变了, 棋盘乱
board.forEach((unit, i) => {
  if (!unit) return;
  const cell = cellmap.tiles[i];  // 假设第 i 个 hex 对应第 i 个 unit, 错
  renderUnitAt(cell.col, cell.row, unit);
});
```

**修法**: `Map<HexKey, Unit>` 遍历, 用 unit.position 反查 cell.

---

## 五 · 配套机制

| 铁律 | 联动点 |
|---|---|
| `cross-end-board-consistency.md` | shared-board 派出的事件 schema 含 `hexKey`, 不含 `slotIdx`. 下游端只能拿 hexKey. |
| `test-pyramid.md` | 玩家视角不变量 (I-1 ~ I-4) 是状态机驱动测的硬要求, statemachine.md 必须显式列 |
| `feedback_skeleton_planning_over_soft_prompt.md` (memory) | "BoardState = Map<HexKey, Unit>" 在规划骨架的接口契约阶段锁死, 不靠 prompt 提醒玩家视角 |
| `feedback_100pct_required_goes_to_skeleton.md` (memory) | "100% 必做的事写进骨架" — 数据模型主键是骨架硬约束 |

---

## 六 · 一句话总览

数据状态主键 = 玩家可见坐标 (`Map<HexKey, Unit>`), action 入参锁视觉坐标, drop handler 不算几何二次, render 用主键反查, 重叠 / 越界在 action 严锚, 玩家视角不变量 (I-1 ~ I-4) 必须有状态转移测 + 红绿对照. array index 锚位是反模式, 即使能跑也要拒.
