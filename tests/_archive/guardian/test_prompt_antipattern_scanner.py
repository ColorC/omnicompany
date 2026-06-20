# [OMNI] origin=claude-code domain=tests/guardian ts=2026-04-28T00:00:00Z type=test
"""PromptAntiPatternScanWorker 测试 · OMNI-090/091/092.

mock 5 项:
  T1: AST 抽 prompt 模块级常量 (含/不含 prompt token)
  T2: AST 兜底抽 system="..." 字面量
  T3: JSON 提取 fence + 裸 JSON
  T4: Worker e2e (mock LLM 返 clean) — audit 落 dismissed records
  T5: Worker e2e (mock LLM 返 OMNI-091 finding) — finding + confirmed audit + 缓存命中

e2e 真 LLM (1 项, 默认 skip):
  T6: 跑真 qwen-3.6-plus 扫一段 prompt; 需要 THE_COMPANY_API_KEY.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from omnicompany.packages.services.guardian.workers.prompt_antipattern_scanner import (
    PromptAntiPatternScanWorker,
    PromptCandidate,
    extract_prompts,
    iter_target_files,
    _extract_review_json,
    _compute_prompt_text_sha16,
    _compute_rule_version,
)
from omnicompany.protocol.anchor import VerdictKind


# ══════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════

@pytest.fixture
def tmp_repo(tmp_path, monkeypatch):
    """临时 repo · 必备目录骨架, 让 _project_root 指向 tmp_path."""
    (tmp_path / "data" / "services" / "guardian" / "audit").mkdir(parents=True)
    (tmp_path / "data" / "services" / "guardian" / "prompt-scan").mkdir(parents=True)
    services = tmp_path / "src" / "omnicompany" / "packages" / "services"
    services.mkdir(parents=True)

    # patch _project_root
    monkeypatch.setattr(
        "omnicompany.core.config._project_root",
        lambda: tmp_path,
    )
    # patch resolve_service_data_dir 也走 tmp_path
    def _fake_resolve(svc):
        return tmp_path / "data" / "services" / svc
    monkeypatch.setattr(
        "omnicompany.core.config.resolve_service_data_dir",
        _fake_resolve,
    )
    return tmp_path


def _make_worker_file(services_dir: Path, name: str, content: str) -> Path:
    """在 tmp services 下生成一个 service/<name>/workers/test.py."""
    svc = services_dir / name
    workers = svc / "workers"
    workers.mkdir(parents=True, exist_ok=True)
    f = workers / "test.py"
    f.write_text(content, encoding="utf-8")
    return f


def _stub_llm_response(text_content: str):
    """构造 LLMClient.call 的返回对象 (含 .content list of blocks)."""
    class _Block:
        def __init__(self, text):
            self.text = text
            self.type = "text"
    class _Resp:
        def __init__(self, t):
            self.content = [_Block(t)]
    return _Resp(text_content)


# ══════════════════════════════════════════════════════════════
# T0 · iter_target_files 三形态 scope 都对
# ══════════════════════════════════════════════════════════════

def test_t0_iter_target_files_three_scopes(tmp_repo):
    services = tmp_repo / "src" / "omnicompany" / "packages" / "services"
    f1 = _make_worker_file(services, "alpha", '_ALPHA_PROMPT = """足够长的 alpha prompt 测试样本, 30+ 字符够."""\n')
    f2 = _make_worker_file(services, "beta",  '_BETA_PROMPT  = """足够长的 beta prompt 测试样本, 30+ 字符够."""\n')

    # 形态 A: services/ 父级 — 应抽到两个 service
    files_parent = iter_target_files(services)
    assert len(files_parent) == 2

    # 形态 B: 单个 service 子目录 — 应只抽自己的
    alpha_svc = services / "alpha"
    files_single_svc = iter_target_files(alpha_svc)
    assert len(files_single_svc) == 1
    assert files_single_svc[0] == f1

    # 形态 C: 单文件 — 直接抽它
    files_single = iter_target_files(f1)
    assert files_single == [f1]


# ══════════════════════════════════════════════════════════════
# T1 · AST 抽 prompt 模块级常量
# ══════════════════════════════════════════════════════════════

def test_t1_extract_module_const(tmp_repo):
    services = tmp_repo / "src" / "omnicompany" / "packages" / "services"
    fpath = _make_worker_file(services, "foo", '''
"""模块 docstring 不抽."""

_FOO_SYSTEM_PROMPT = """这是一段足够长的 prompt, 含原则给 LLM 看. 你必须自洽不引外部, 不写枚举, 不锁具体方案. 写满足什么. 这样长度够过 30 字符门槛."""

_BAR_TEMPLATE = """另一段 prompt 模板, 同样需要 LLM 复核, 长度也够, 内容足够丰富, 这是测试样本。"""

SHORT = "不抽 短"

_NOT_PROMPT_VAR = "这个名字不含 token, 不抽."

_USER_MESSAGE_GUIDE = """这段名字含 USER + GUIDE 两个 token, 应该抽出来, 长度也够, 测试。"""
''')
    candidates = extract_prompts(fpath, tmp_repo)
    names = sorted(c.prompt_name for c in candidates)
    assert names == ["_BAR_TEMPLATE", "_FOO_SYSTEM_PROMPT", "_USER_MESSAGE_GUIDE"]
    for c in candidates:
        assert c.method == "module_const"
        assert len(c.text) >= 30


# ══════════════════════════════════════════════════════════════
# T2 · AST 兜底抽 system="..." 字面量
# ══════════════════════════════════════════════════════════════

def test_t2_extract_system_arg(tmp_repo):
    services = tmp_repo / "src" / "omnicompany" / "packages" / "services"
    fpath = _make_worker_file(services, "foo", '''
def call_llm():
    response = client.call(
        messages=[{"role": "user", "content": "hi"}],
        system="这是一段足够长的 system 参数 prompt, 直接传字符串不存常量, 长度大于 30 字符够了, 测试用.",
    )
    return response
''')
    candidates = extract_prompts(fpath, tmp_repo)
    assert len(candidates) == 1
    assert candidates[0].method == "system_arg"
    assert "system 参数 prompt" in candidates[0].text


# ══════════════════════════════════════════════════════════════
# T3 · JSON 提取
# ══════════════════════════════════════════════════════════════

def test_t3_json_extract_fence():
    raw = """前导文字
```json
{"verdict": "clean", "findings": [], "summary": "OK"}
```
末尾杂音"""
    parsed = _extract_review_json(raw)
    assert parsed == {"verdict": "clean", "findings": [], "summary": "OK"}


def test_t3_json_extract_bare():
    raw = '   {"verdict": "issues_found", "findings": [{"rule_id": "OMNI-090"}], "summary": "x"}'
    parsed = _extract_review_json(raw)
    assert parsed is not None
    assert parsed["verdict"] == "issues_found"


def test_t3_json_extract_garbage():
    assert _extract_review_json("纯文本无 json") is None
    assert _extract_review_json("") is None
    assert _extract_review_json("```json\n不是有效 JSON\n```") is None


# ══════════════════════════════════════════════════════════════
# T4 · Worker e2e (mock LLM 返 clean)
# ══════════════════════════════════════════════════════════════

def test_t4_worker_clean_run(tmp_repo):
    services = tmp_repo / "src" / "omnicompany" / "packages" / "services"
    _make_worker_file(services, "foo", '''
_FOO_SYSTEM_PROMPT = """一段干净 prompt, 自洽, 写原则不写枚举, 写满足什么不写怎么做. 测试用样本, 长度足够."""
''')

    fake_clean_response = _stub_llm_response(
        '```json\n{"verdict": "clean", "summary": "三原则均满足", "findings": []}\n```'
    )

    with patch(
        "omnicompany.runtime.llm.llm.LLMClient"
    ) as MockLLM:
        instance = MockLLM.return_value
        instance.call.return_value = fake_clean_response

        worker = PromptAntiPatternScanWorker()
        verdict = worker.run({})

    assert verdict.kind == VerdictKind.PASS
    out = verdict.output
    assert out["prompts_total"] == 1
    assert out["prompts_scanned"] == 1
    assert out["prompts_cached"] == 0
    assert out["findings"] == []
    # 三条规则都写一条 dismissed audit
    assert out["audit_records_appended"] == 3
    assert out["by_verdict"].get("dismissed", 0) == 3


# ══════════════════════════════════════════════════════════════
# T5 · Worker e2e (mock LLM 返 OMNI-091 finding) + 缓存命中
# ══════════════════════════════════════════════════════════════

def test_t5_worker_finding_then_cache_hit(tmp_repo):
    services = tmp_repo / "src" / "omnicompany" / "packages" / "services"
    _make_worker_file(services, "bar", '''
_BAR_SYSTEM_PROMPT = """对所有用户输入按以下处理: 若是A类型, 这样回. 若是B类型, 那样回. 若是C类型, 又那样回. 笨拙穷举的样本, 测试 OMNI-091."""
''')

    fake_finding_response = _stub_llm_response(
        '```json\n'
        '{"verdict": "issues_found", "summary": "笨拙枚举",'
        ' "findings": [{"rule_id": "OMNI-091", "severity": "MEDIUM",'
        ' "evidence": "若是A类型...若是B类型...若是C类型...",'
        ' "fix_hint": "改写为给原则让 LLM 自判", "confidence": 0.85}]}\n'
        '```'
    )

    with patch("omnicompany.runtime.llm.llm.LLMClient") as MockLLM:
        instance = MockLLM.return_value
        instance.call.return_value = fake_finding_response

        worker = PromptAntiPatternScanWorker()
        verdict = worker.run({})

    assert verdict.kind == VerdictKind.PASS
    out = verdict.output
    assert len(out["findings"]) == 1
    f = out["findings"][0]
    assert f["rule_id"] == "OMNI-091"
    assert f["severity"] == "MEDIUM"
    assert "若是A类型" in f["evidence"]
    assert f["from_cache"] is False
    # confirmed: 1 (OMNI-091), dismissed: 2 (其他两条规则)
    assert out["by_verdict"]["confirmed"] == 1
    assert out["by_verdict"]["dismissed"] == 2

    # ── 第二次跑应该全缓存命中, LLM 不被调 ──
    with patch("omnicompany.runtime.llm.llm.LLMClient") as MockLLM2:
        instance2 = MockLLM2.return_value
        instance2.call.side_effect = AssertionError("不该再调 LLM, 应走缓存")

        worker = PromptAntiPatternScanWorker()
        verdict2 = worker.run({})

    assert verdict2.kind == VerdictKind.PASS
    out2 = verdict2.output
    assert out2["prompts_total"] == 1
    assert out2["prompts_scanned"] == 0
    assert out2["prompts_cached"] == 1
    # finding 从缓存复用 (只有 confirmed 那条)
    assert len(out2["findings"]) == 1
    assert out2["findings"][0]["from_cache"] is True


# ══════════════════════════════════════════════════════════════
# T5b · Worker 同时支持两种 input_data 形态 (dispatcher 嵌套 + 直调平铺)
# ══════════════════════════════════════════════════════════════

def test_t5b_input_data_two_shapes(tmp_repo):
    """dispatcher 传 {FORMAT_IN: payload} 嵌套, 直调传 payload 本体. 都识别 scope."""
    services = tmp_repo / "src" / "omnicompany" / "packages" / "services"
    _make_worker_file(services, "alpha", '''_A_PROMPT = """alpha 段 prompt 内容, 长度足够过 30 字符门槛, 测试样本一."""
''')
    _make_worker_file(services, "beta",  '''_B_PROMPT = """beta 段 prompt 内容, 长度足够过 30 字符门槛, 测试样本二."""
''')

    fake_clean = _stub_llm_response('```json\n{"verdict":"clean","findings":[],"summary":"ok"}\n```')

    alpha_path = str(services / "alpha")

    # 形态 1: 直调平铺 — input_data = {"scope": ...}
    with patch("omnicompany.runtime.llm.llm.LLMClient") as M:
        M.return_value.call.return_value = fake_clean
        worker = PromptAntiPatternScanWorker()
        v = worker.run({"scope": alpha_path})
    assert v.output["prompts_total"] == 1  # 只 alpha

    # 形态 2: dispatcher 嵌套 — input_data = {FORMAT_IN: {"scope": ...}}
    with patch("omnicompany.runtime.llm.llm.LLMClient") as M:
        M.return_value.call.return_value = fake_clean
        worker = PromptAntiPatternScanWorker()
        v = worker.run({"guardian.prompt-scan-request": {"scope": alpha_path}})
    assert v.output["prompts_total"] == 1  # 同样只 alpha (不该跳到默认全 services 扫到 beta)


# ══════════════════════════════════════════════════════════════
# T6 · LLM 调用失败容错
# ══════════════════════════════════════════════════════════════

def test_t6_worker_llm_failure(tmp_repo):
    services = tmp_repo / "src" / "omnicompany" / "packages" / "services"
    _make_worker_file(services, "qux", '''
_QUX_SYSTEM_PROMPT = """一段需要被复核的 prompt, 但 LLM 会挂掉, 看 Worker 是否容错落 uncertain, 测试用."""
''')

    with patch("omnicompany.runtime.llm.llm.LLMClient") as MockLLM:
        instance = MockLLM.return_value
        instance.call.side_effect = RuntimeError("network down")

        worker = PromptAntiPatternScanWorker()
        verdict = worker.run({})

    assert verdict.kind == VerdictKind.PASS
    out = verdict.output
    assert out["findings"] == []
    # 三条规则各一条 uncertain
    assert out["by_verdict"]["uncertain"] == 3


# ══════════════════════════════════════════════════════════════
# T7 · sha16 / rule_version 稳定性
# ══════════════════════════════════════════════════════════════

def test_t7_sha_stability():
    text = "abc def 中文"
    s1 = _compute_prompt_text_sha16(text)
    s2 = _compute_prompt_text_sha16(text)
    assert s1 == s2
    assert len(s1) == 16

    desc = "rule description body"
    v1 = _compute_rule_version(desc)
    v2 = _compute_rule_version(desc)
    assert v1 == v2
    assert v1.startswith("v")
    # 改 description 即版本变
    v3 = _compute_rule_version(desc + " modified")
    assert v3 != v1


# ══════════════════════════════════════════════════════════════
# T_e2e · 真 LLM (默认 skip, THE_COMPANY_API_KEY 时跑)
# ══════════════════════════════════════════════════════════════

@pytest.mark.skipif(
    not os.environ.get("THE_COMPANY_API_KEY"),
    reason="需要 THE_COMPANY_API_KEY 环境变量"
)
def test_e2e_real_llm(tmp_repo):
    """e2e 真 LLM: 喂一段明显违 OMNI-091 的 prompt 看 LLM 真能识别."""
    services = tmp_repo / "src" / "omnicompany" / "packages" / "services"
    _make_worker_file(services, "test_e2e", '''
_BLATANT_BAD_PROMPT = """对每一种用户输入按以下分类处理:
- 若用户问 A: 回 "你好"
- 若用户问 B: 回 "再见"
- 若用户问 C: 回 "好的"
- 若用户问 D: 回 "知道了"
- 若用户问 E: 回 "可以"
- 若用户问 F: 回 "明白"
- 若用户问 G: 回 "ok"
全部按上述对应回. 不要超出这些分类."""
''')
    worker = PromptAntiPatternScanWorker()
    verdict = worker.run({})
    assert verdict.kind == VerdictKind.PASS
    out = verdict.output
    print(f"\ne2e LLM 结果: {out['by_rule']}, by_verdict={out['by_verdict']}")
    print(f"finding 数: {len(out['findings'])}")
    for f in out["findings"]:
        print(f"  {f['rule_id']} [{f['severity']}] evidence: {f['evidence'][:80]}")
    # 期望至少抓到 OMNI-091 (笨拙枚举); 不强断言以容 LLM 不稳定
