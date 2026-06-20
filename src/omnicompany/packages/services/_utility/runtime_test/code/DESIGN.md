
# code_runtime_test · 代码产物测试团队

## 1 · 名称与定位

`code_runtime_test` 是测试**代码产物类型**目标团队 (例: csv-to-md 产 markdown 文本) 的测试团队. 跟 `absorption_runtime_test` 平行, 同为特化测试团队, 但对应不同产物形态.

> ⚠️ "代码产物 / absorption" 是当前两个有具体测试团队的特化领域, **不是穷尽分类**. 真通用层 (针对 target 生成假设的 meta 层) 在 Phase B/C 立, 见 `docs/plans/[2026-04-26]VERIFICATION-AS-HYPOTHESIS-METHOD/plan.md`.

**关键差别**: 代码产物**有 ground truth** (人写的标杆输出). 验证方式以**对标 + 边界探测**为主, 不需要多源 LLM 互验.

立项: 2026-04-26 · sediment 自 [tests/teams/csv_to_md/test_contract.py](../../../../../../../data/_workspaces/team_builder/repo_abs_140156/tests/teams/csv_to_md/test_contract.py) 现成 contract test 模式.

## 2 · 职责

接收用例集 (input fixture + expected output 对), 跑目标团队, 验证:
- 路 1 标杆对标: success cases byte-diff 跟 expected 比
- 路 2 错误处理: error cases verdict + diagnosis 关键词检查
- 路 3 重现性: 同 input 跑两次 byte-identical
- 路 4 边界探测 (可选): 喂极端 input 看健壮性

## 3 · 输入与输出

### 3.1 输入 `code_runtime_test.target_spec`

```json
{
  "target_team_id": "csv-to-md",
  "test_cases": [
    {"name": "case_1_basic", "kind": "success", "input": {"path": "..."}, "expected_path": "..."},
    {"name": "error_file_not_found", "kind": "error", "input": {...}, "expected_verdict": "FAIL", "diagnosis_keywords": ["not found"]},
    {"name": "case_repro", "kind": "reproducibility", "input": {...}}
  ],
  "output_extractor": "report_markdown"
}
```

### 3.2 输出 `code_runtime_test.portrait`

跟 absorption 同形态 (verdict/三问 brief/做得好/漏 句子列表), 但**梯度更细** — 因为代码产物有量化:

- success cases byte-exact 比例 (PASS 严要求)
- 平均 byte_diff_count (即使 fail 也告诉差多少)
- error cases diagnosis 命中关键词比例
- 重现性 byte-identical (二元)

## 4 · 拓扑

```
TargetIngressWorker (HARD)
  ↓
  ├──→ GoldenContractRunner (HARD · 跑 success cases · diff)
  ├──→ ErrorPathRunner (HARD · 跑 error cases · 验 verdict + diag)
  └──→ ReproducibilityRunner (HARD · 同 input 跑 2 次 · byte 比)
        ↓ 3 路 fan-in
   PortraitAssemblerWorker (HARD · sink)
```

5 节点. 全 HARD, 无 LLM, 跑得快 (秒级到分钟级取决于目标团队).

## 5 · Material (5 个)

| ID | producer | consumer |
|---|---|---|
| `code_runtime_test.target_spec` | 外部 | TargetIngress |
| `code_runtime_test.target_metadata` | TargetIngress | 3 验证器 |
| `code_runtime_test.golden_evidence` | GoldenContractRunner | PortraitAssembler |
| `code_runtime_test.error_evidence` | ErrorPathRunner | PortraitAssembler |
| `code_runtime_test.reproducibility_evidence` | ReproducibilityRunner | PortraitAssembler |
| `code_runtime_test.portrait` | PortraitAssembler | sink |

(实际 6 个 material · entry/sink + 4 中间)

## 6 · 边界与约束

### 6.1 全 HARD · 不调 LLM

代码产物有 ground truth, 不需要 LLM 互验. byte-diff 是确定性算法.

### 6.2 嵌套 dispatch · subprocess

跟 absorption_runtime_test 一样用 subprocess 跑目标 dispatch.

### 6.3 反模式禁令

按 [feedback_semantic_sentences_not_classification](C:/Users/user/.claude/projects/e--workspace/memory/feedback_semantic_sentences_not_classification.md):
- portrait 字段全自然语言句子
- 物理度量 (byte_diff_count / pass_rate / elapsed_sec) 允许
- 禁打分/标签

### 6.4 适用产物类型

仅适合**代码产物** (有确定性 ground truth):
- ✅ csv-to-md (input csv → output markdown · 有标杆)
- ✅ team_builder (input 需求 → output Python 代码 · 标杆是"能编译能跑")
- ✅ config_table生成 (input 表 → output csv · 有 historical baseline diff)
- ❌ repo_absorption (absorption 类 · 走 absorption_runtime_test)

### 6.5 红绿基线在哪做

每个 verifier 都有内置红绿:
- GoldenContractRunner 的"红"是"故意改坏 expected" (verifier 应捕到), "绿"是"用 expected 当 actual" (verifier 应认 100% match)
- 校准脚本在 scratch/calibration_<verifier>.py
