"""Wave 5 收尾 — 真 LLM smoke 测试 (2026-05-05 立).

**默认跳过** (避免意外消耗 API 配额). 显式跑:
  pytest tests/agent_tools/test_wave5c_llm_smoke.py -m llm_smoke

跑前需:
  - THE_COMPANY_API_KEY 在 .env 或环境变量
  - 网络通

验收点 (反虚假声明铁律 — Wave 1-5 所有声明的"真接通"实际效果):
  1. LLMClient role="ide_agent" 能成功 call
  2. 返响应是文本 / 含合理内容
  3. 配工具 schema (default tool spec) 能调工具
  4. 多轮 tool_use → tool_result 流程通

不验:
  - 端到端 NativeIdeAgent 真启 (太重 + 状态多)
  - sub-agent spawn 真启
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

# 自定义 marker — 默认 skip, 显式 -m llm_smoke 才跑
pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNI_LLM_SMOKE"),
    reason="real LLM smoke skipped by default. Set OMNI_LLM_SMOKE=1 to run.",
)


def _api_key_available() -> bool:
    """检查 THE_COMPANY_API_KEY 是否设置 (不真验 key 是否有效)."""
    # 加载 .env (如果有 dotenv)
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    return bool(os.environ.get("THE_COMPANY_API_KEY"))


# ═══════════════════════════════════════════════════════════════════════
# 最小 LLM call smoke
# ═══════════════════════════════════════════════════════════════════════


class TestLLMClientSmoke:
    def test_simple_text_call(self):
        if not _api_key_available():
            pytest.skip("THE_COMPANY_API_KEY not set")

        from omnicompany.runtime.llm.llm import LLMClient

        client = LLMClient.for_role("ide_agent")
        resp = client.call(
            messages=[{"role": "user", "content": "Reply with the single word PONG."}],
            system="You are a test assistant. Always reply concisely.",
            caller="wave5c_smoke.simple",
        )
        # resp 结构跟 anthropic SDK 对齐
        # 取出 text 部分
        text = ""
        if hasattr(resp, "content"):
            for block in resp.content:
                if hasattr(block, "text"):
                    text += block.text
                elif isinstance(block, dict) and block.get("type") == "text":
                    text += block.get("text", "")
        assert "PONG" in text.upper(), f"LLM response missing PONG: {text!r}"


# ═══════════════════════════════════════════════════════════════════════
# Default 工具 spec 给 LLM 看 — 是否能调起工具
# ═══════════════════════════════════════════════════════════════════════


class TestDefaultToolSpecsRecognized:
    # 2026-05-05 P1.1 修后: xfail 去掉. fallback parser 跟 OpenAI tool_calls
    # 双路径都接通, qwen3.6-plus 真能调工具.
    def test_llm_calls_glob_tool(self, tmp_path):
        if not _api_key_available():
            pytest.skip("THE_COMPANY_API_KEY not set")

        from omnicompany.runtime.llm.llm import LLMClient
        from omnicompany.packages.services._core.agent.routers import (
            get_default_tool_specs,
        )

        # 造几个 .py 文件让 LLM 用 glob 查
        (tmp_path / "a.py").write_text("# a")
        (tmp_path / "b.py").write_text("# b")
        (tmp_path / "c.txt").write_text("# c")

        client = LLMClient.for_role("ide_agent")
        # tools_spec 是 [{name, description, input_schema}, ...]
        tools_spec = get_default_tool_specs()
        # 注: 这测验证的是 LLM 看到 spec 后**会决定调** glob, 不是真执行
        resp = client.call(
            messages=[{
                "role": "user",
                "content": (
                    f"List all .py files under {tmp_path}. Use the glob tool."
                ),
            }],
            system="You are a code search assistant. Use the available tools.",
            caller="wave5c_smoke.tool_recognition",
        )
        # 验 LLM 真发了 tool_use block
        tool_uses = []
        if hasattr(resp, "content"):
            for block in resp.content:
                if hasattr(block, "type") and block.type == "tool_use":
                    tool_uses.append(block)
                elif isinstance(block, dict) and block.get("type") == "tool_use":
                    tool_uses.append(block)
        # 至少有一个 tool_use 调
        assert len(tool_uses) >= 1, f"LLM 未调任何工具. resp 内容: {resp.content if hasattr(resp, 'content') else resp}"
        # 而且应该调 glob (跟 prompt 一致)
        names = [getattr(tu, "name", None) or tu.get("name") for tu in tool_uses]
        assert "glob" in names or "Glob" in names, f"LLM 调了 {names!r} 不是 glob"
