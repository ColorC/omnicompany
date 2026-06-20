# [OMNI] origin=ai-ide domain=research ts=2026-06-14T00:00:00Z type=prompts status=active
# [OMNI] summary="research domain 各 LLM 步骤的系统提示词 + 结构化 schema(规划/单页摘要/抽取/反思/综合/核源)。"
# [OMNI] why="提示词集中一处便于调;schema 给 call_json 约束输出。对齐开源 SOTA(STORM 多视角拆题、open_deep_research 引用接地、anthropic 委派四件套)。"
# [OMNI] tags=research,prompts,schema
"""research domain 的提示词与 schema。

模型档位: 拆题/反思/核源 = 中端 MID_MODEL;单页摘要/抽取/综合 = 便宜默认档。
"""

from __future__ import annotations

MID_MODEL = "qwen3.6-plus"  # 拆错/核错代价大的步骤走中端;苦力仍便宜档(deepseek-v4-pro)


# ── 规划/拆题(先搜后拆 + 多视角 + 互不重叠 + 复杂度档位)──────────────────
PLANNER_SYSTEM = (
    "你是公开调研的规划员。给你一个题目和一小撮背景检索片段,把题目拆成**互不重叠**的子主题,"
    "每个子主题配齐:goal(要查清什么)、perspective(从哪个视角问 —— 如 机制/对比选型/历史与争议/"
    "反对方案与替代/落地与坑/基础覆盖)、queries(2-3 个具体搜索词,不同视角用不同词)、boundary(不碰什么,防与别的子主题重叠)。"
    "**视角要多样**,至少含一个'基础覆盖'兜底视角 + 一个'冷门/反对/替代方案'视角(防只顺着主流钻、漏掉小众但有效的)。"
    "拆几个按复杂度:简单事实=1,对比类=2-4,复杂=最多5。背景片段是先验,别人写过的角度就是你不该漏的角度。"
    "再写一句 brief:这次调研到底要回答什么。全中文。"
)
PLANNER_SCHEMA = {
    "type": "object",
    "properties": {
        "brief": {"type": "string"},
        "complexity": {"type": "string"},
        "subtopics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "goal": {"type": "string"},
                    "perspective": {"type": "string"},
                    "queries": {"type": "array", "items": {"type": "string"}},
                    "boundary": {"type": "string"},
                },
                "required": ["goal", "queries"],
            },
        },
    },
    "required": ["subtopics"],
}


# ── 单页摘要(第一道 token 收缩:整页→要点,保事实保来源)─────────────────
PAGE_SUMMARY_SYSTEM = (
    "把这一页内容按'对这个子主题有用的事实'压成要点,逐字保留关键信息和数字,只删与子主题无关/重复的;"
    "不概括成空话、不编造页面里没有的东西。全中文,200 字内。"
)
PAGE_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {"summary": {"type": "string"}},
    "required": ["summary"],
}


# ── 子主题抽取(从该子主题的几页材料里抽带来源的发现)──────────────────────
EXTRACT_SYSTEM = (
    "你是子研究员。只根据给你的几页材料(title/url/summary),抽出关于这个子主题的发现 findings。"
    "每条 finding 写一句具体结论 claim + 它依据的 source_url(必须是材料里出现过的 url)。"
    "材料里没支撑的别写。客观、给证据、不打分。全中文。"
)
EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "source_url": {"type": "string"},
                },
                "required": ["claim"],
            },
        },
    },
    "required": ["findings"],
}


# ── 反思(看覆盖账本指缺口 + 打捞未被用上的检索料)─────────────────────────
REFLECT_SYSTEM = (
    "你是编排者。给你题目、已覆盖的视角、已收集的结论 claims、以及'撞见但没用上'的检索片段标题(salvage 池)。"
    "判断:① covered —— 已经覆盖得不错的视角;② open_gaps —— 还**明显缺**的角度(只列真缺的,覆盖够了就给空数组),"
    "每个缺口给 goal/perspective/queries(2-3 个搜索词),用于下一轮再查;"
    "③ salvage —— 从'撞见但没用上'的标题里,挑出与题目相关、但和已问角度都不同的,变成新焦点(可空)。"
    "宁可少列缺口也别硬凑(防无界发散)。全中文。"
)
REFLECT_SCHEMA = {
    "type": "object",
    "properties": {
        "covered": {"type": "array", "items": {"type": "string"}},
        "open_gaps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "goal": {"type": "string"},
                    "perspective": {"type": "string"},
                    "queries": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["goal", "queries"],
            },
        },
        "salvage": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["open_gaps"],
}


# ── 综合(接地带引用:唯一 url 连续编号 + 不编造)──────────────────────────
SYNTH_SYSTEM = (
    "你是综合 worker。把各子研究员收集的带来源发现,综合成一份客观、不打分、带来源的调研结论。"
    "只根据给你的 findings 下结论,绝不编造;findings 没覆盖的就写进 perspectives_open(还没覆盖的角度)。"
    "summary 2-4 句概述;findings 是要点,每条尽量带它依据的 source_url;"
    "keywords/aliases 给题目的关键词与别名/同义词(为日后查重与召回)。全中文。"
)
SYNTH_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "source_url": {"type": "string"},
                },
                "required": ["claim"],
            },
        },
        "keywords": {"type": "array", "items": {"type": "string"}},
        "aliases": {"type": "array", "items": {"type": "string"}},
        "perspectives_open": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "findings"],
}


# ── 核源(对抗式:抓原始来源,判这条断言站不站得住)────────────────────────
VERIFY_SYSTEM = (
    "你是核源员。给你一条结论 claim 和它声称的来源页正文。**只看这页正文**判断它支不支持这条 claim:"
    "supported(明确支持)/ partial(沾边但不充分)/ unsupported(页里找不到支撑或矛盾)。"
    "默认从严:看不到明确支撑就别给 supported。给一句 note 说依据。全中文。"
)
VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "support": {"type": "string", "enum": ["supported", "partial", "unsupported"]},
        "note": {"type": "string"},
    },
    "required": ["support"],
}
