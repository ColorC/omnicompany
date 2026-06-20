# [OMNI] origin=claude-code domain=services/hypothesis_library/universal_hypotheses ts=2026-04-27T00:00:00Z type=data
# [OMNI] material_id="material:services.learning.hypothesis_library.universal_hypotheses.py"
"""4 条候选地基假设 · 跨大多数产物可能适用.

来源: memory `feedback_test_is_hypothesis_method` §通用假设清单.

⚠️ 候选 ≠ 定论. 跑多类产物校准后可能修订.
"""
from __future__ import annotations

from .hypothesis import Hypothesis


H_STABLE = Hypothesis(
    id="stable",
    description=(
        "好产物应该在同输入下跨次产出相似的内容. 不稳定意味产物里有大量随机/无信号成分, "
        "再多重复也无法收敛."
    ),
    when_applicable=(
        "几乎所有产物 (代码 / 知识 / 故事 / config_table / UI / 决策) 都该过这条. "
        "唯一不适用是有意要随机性的场景 (如 noise generator / 蒙特卡洛模拟产输出)."
    ),
    verification_template=(
        "同输入跑 N 次 (N≥2), 比较两次产物的相似度. 相似度的具体定义因产物而异: "
        "代码产物用字节比, 文本产物用 set 重叠 / 主题重叠, 故事用结构比对. "
        "稳定性高 → 信号强; 稳定性低 → 信号弱 (但稳定不一定对, 必要不充分)."
    ),
    examples=(
        "absorption: 跨次同 repo_path 抓的 file set 重叠 ≥50%",
        "csv-to-md: 同 csv input 两次输出 byte-identical (100%)",
        "故事生成 (假想): 跨场景同 NPC 名字一致, 时间线无矛盾",
        "config_table (假想): 同 xlsm 两次导出 csv byte-identical",
    ),
    category="universal",
    provenance="memory feedback_test_is_hypothesis_method §通用假设清单",
)


H_HONEST = Hypothesis(
    id="honest",
    description=(
        "好产物里的引用 / 锚点 / 数字 / 文件路径 / API 名应当在源真实存在, 不是 LLM 编造."
    ),
    when_applicable=(
        "凡产物含外部锚点 (文件路径 / 行号 / 函数名 / 数据值 / URL) 都该过. "
        "不适用纯创意类产物 (诗 / 抽象画) — 它们不主张外部对应."
    ),
    verification_template=(
        "扫产物里所有外部锚点, 程序化校验存在性: "
        "文件路径 → Path.is_file(); 函数名 → 真有 def; 数据值 → 真在表里; URL → HTTP 200. "
        "命中率高 → 诚实; 命中率低 → LLM 在编造."
    ),
    examples=(
        "absorption: 提案 reference_code.{file, line} 必须在 repo 里真存在",
        "代码生成: 引用的 import 模块应真有 (能 importlib 起来)",
        "故事 (假想): 涉历史事件的部分跟知识库不矛盾",
        "数据分析报告 (假想): 引用的数字应能在原数据集复现",
    ),
    category="universal",
    provenance="memory feedback_test_is_hypothesis_method §通用假设清单",
)


H_ROBUST = Hypothesis(
    id="robust",
    description=(
        "好产物对错误输入应明确失败 (verdict=FAIL + 可读 diagnosis), 不假装成功 / 不静默吞错."
    ),
    when_applicable=(
        "凡有明确对错边界的产物 (代码 / API / config_table / 协议层产物). "
        "不适用模糊创作类 (任意 input 都该有创意 output 的场景)."
    ),
    verification_template=(
        "构造一组明显错的输入 (空字符串 / 不存在路径 / 类型不符 / 越界数值), "
        "跑 target, 检查 verdict 应是 FAIL/PARTIAL 而非 PASS, diagnosis 含可识别关键词. "
        "正确失败率高 → 健壮; 假装成功率高 → 脆."
    ),
    examples=(
        "csv-to-md: input='不存在路径' → verdict=FAIL + diagnosis 含 'not found'",
        "代码生成: 错误的需求描述 → 应回 verdict=FAIL 不强行编代码",
        "config_table (假想): xlsm 缺关键 sheet → 应明确报错而非 silently 产残缺 csv",
        "API: 鉴权失败应回 401 不回 200",
    ),
    category="universal",
    provenance="memory feedback_test_is_hypothesis_method §通用假设清单",
)


H_OBSERVABLE = Hypothesis(
    id="observable",
    description=(
        "好产物的过程应当含足够信息让人理解 — trace 可读 / 字段完整 / diagnosis 清晰. "
        "不该是黑盒."
    ),
    when_applicable=(
        "几乎所有 OmniCompany 产物 (因团队铁律 'agent node loop 必挂 EventBus + 全 Material 落盘'). "
        "不适用跨语言/跨进程的纯 1-step 转换 (这种过程本就极简)."
    ),
    verification_template=(
        "扫 events.db / 产物的 trace, 检查关键事件是否齐 (LLM 调用入参 / 出参 / tool 调用 / 中间 Material). "
        "缺字段 → 不可观察 (调试困难); 全字段 + 时序齐 → 可观察 (可 replay)."
    ),
    examples=(
        "agent_node_loop: 必挂 EventBus, 所有 Format 落盘",
        "absorption: events.db 里 source=repo_absorption 应有完整 LLM/tool trace",
        "故事生成 (假想): 应记录每个 NPC 决策的依据 (规则/状态变量), 不是黑盒",
        "API 网关 (假想): structured logging + request_id 关联",
    ),
    category="universal",
    provenance="memory feedback_test_is_hypothesis_method §通用假设清单",
)


UNIVERSAL_HYPOTHESES: tuple[Hypothesis, ...] = (
    H_STABLE,
    H_HONEST,
    H_ROBUST,
    H_OBSERVABLE,
)
