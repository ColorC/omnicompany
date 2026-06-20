# [OMNI] origin=ai-ide domain=tests/services/_diagnosis/doctor ts=2026-05-07T07:35:00Z type=test status=active agent=ai-ide
# [OMNI] summary="pytest 单元测 HypothesisV1Upgrader — 验 source_kind=code → 'code-derived' / source_path 在 map 各档 / risk 关键词派生"
# [OMNI] why="V1 留议大动作清单 — 给 source_kind=code 假设加 'code-derived' authority 类别. 元规范第 2 条立类必带合规样本"
# [OMNI] tags=test,pytest,builder,hypothesis-upgrader,unit-test,code-derived
# [OMNI] material_id="material:tests.services.diagnosis.doctor.test_hypothesis_v1_upgrader.py"
"""pytest 单元测 HypothesisV1Upgrader.

测 case:
- 边界 (空 list / 缺 id / 非 dict)
- source_kind=code → 'code-derived' (V1 新类别核心断言)
- source_path 在 HIGH/MEDIUM/LOW 档分别命中
- source_path 不在 map 且非 code → unknown
- statement 关键词派生 risk (high/medium/low)
- 默认值幂等 (已带字段不覆盖)
- 批量统计分布
"""
from __future__ import annotations

import pytest

from omnicompany.packages.services._diagnosis.doctor.builders import (
    HypothesisV1Upgrader,
    HypothesisV1UpgradeResult,
)


@pytest.fixture
def authority_map():
    """模拟 standards_authority_map.yaml 内容."""
    return {
        "authority_levels": {
            "HIGH": {
                "documents": [
                    {"path": "docs/standards/_global/standards_meta.md"},
                    {"path": "docs/standards/cli/omni-header.md"},
                ]
            },
            "MEDIUM": {
                "documents": [
                    {"path": "docs/standards/_global/llm_first.md"},
                ]
            },
            "LOW": {
                "documents": [
                    {"path": "docs/standards/concepts/worker.md"},
                ]
            },
        }
    }


@pytest.fixture
def upgrader(authority_map):
    return HypothesisV1Upgrader(authority_map=authority_map)


# ── 边界 case ──

def test_upgrade_no_id_returns_none(upgrader):
    assert upgrader.upgrade({"statement": "no id"}) is None


def test_upgrade_batch_skip_non_dict(upgrader):
    result = upgrader.upgrade_batch(["string", 42, None])
    assert result.upgraded == []
    assert len(result.skipped) == 3


def test_upgrade_batch_skip_no_id(upgrader):
    result = upgrader.upgrade_batch([{"statement": "missing id"}])
    assert result.upgraded == []
    assert result.skipped == [("<no-id>", "缺 id")]


# ── source_authority 派生 (V1 核心新类别) ──

def test_source_kind_code_yields_code_derived(upgrader):
    """source_kind=code → 'code-derived' (V1 新类别 — 之前混在 unknown 里)."""
    hyp = {"id": "H-code-001", "source_kind": "code", "source_path": "src/old/worker.py", "statement": "x"}
    up = upgrader.upgrade(hyp)
    assert up.derived_authority == "code-derived"
    assert up.upgraded_dict["source_authority"] == "code-derived"
    assert any("code-derived" in n for n in up.derivation_notes)


def test_source_path_in_high(upgrader):
    hyp = {"id": "H-1", "source_kind": "spec", "source_path": "docs/standards/_global/standards_meta.md", "statement": "x"}
    assert upgrader.upgrade(hyp).derived_authority == "HIGH"


def test_source_path_in_medium(upgrader):
    hyp = {"id": "H-2", "source_kind": "spec", "source_path": "docs/standards/_global/llm_first.md", "statement": "x"}
    assert upgrader.upgrade(hyp).derived_authority == "MEDIUM"


def test_source_path_in_low(upgrader):
    hyp = {"id": "H-3", "source_kind": "spec", "source_path": "docs/standards/concepts/worker.md", "statement": "x"}
    assert upgrader.upgrade(hyp).derived_authority == "LOW"


def test_source_path_not_in_map_and_not_code_is_unknown(upgrader):
    """非 code 且 source_path 不在 map 里 → unknown (跟 code-derived 区分)."""
    hyp = {"id": "H-4", "source_kind": "spec", "source_path": "docs/random/foo.md", "statement": "x"}
    up = upgrader.upgrade(hyp)
    assert up.derived_authority == "unknown"


# ── risk_if_wrong 关键词派生 ──

def test_risk_high_keyword(upgrader):
    hyp = {"id": "H-r1", "statement": "Worker 必须有 FORMAT_OUT"}
    assert upgrader.upgrade(hyp).derived_risk == "high"


def test_risk_high_keyword_negative(upgrader):
    hyp = {"id": "H-r2", "statement": "不得在 worker 内调 LLM"}
    assert upgrader.upgrade(hyp).derived_risk == "high"


def test_risk_medium_keyword(upgrader):
    hyp = {"id": "H-r3", "statement": "应该用 SubmitRouter 提交结果"}
    assert upgrader.upgrade(hyp).derived_risk == "medium"


def test_risk_low_default(upgrader):
    hyp = {"id": "H-r4", "statement": "建议尽量保持简单 -- 但本句以建议开头会命中 medium, 试纯描述"}
    # 这条含"建议" → medium, 不能验 low. 改试纯描述
    hyp_plain = {"id": "H-r5", "statement": "普通描述句子, 无强弱信号"}
    assert upgrader.upgrade(hyp_plain).derived_risk == "low"


def test_risk_should_synonyms_match_medium(upgrader):
    """SHOULD 同义词集 (应优先/宜/最好) 都判 medium.

    2026-05-07 真重跑 25 假设发现 H-2026-05-06-024 含'应优先使用'被判 low,
    应判 medium (建议级). 加 keyword 后修.
    """
    cases = [
        ("应优先使用 X 而非 Y", "应优先"),
        ("Worker 宜采用 X 模式", "宜"),
        ("最好用 X 而非 Y", "最好"),
        ("建议用 SubmitRouter", "建议"),
        ("推荐 X 模式", "推荐"),
    ]
    for statement, kw in cases:
        h = upgrader.upgrade({"id": f"H-{kw}", "statement": statement})
        assert h.derived_risk == "medium", f"'{statement}' (含 {kw!r}) 应判 medium 实际 {h.derived_risk}"


def test_risk_high_keyword_should_take_precedence_over_medium(upgrader):
    """同句含 high (应当) + medium (应优先) 关键词 → 判 high (high 优先级高)."""
    h = upgrader.upgrade({"id": "H-mixed", "statement": "应当如此, 但应优先 X"})
    assert h.derived_risk == "high"


# ── 默认值幂等 ──

def test_existing_v1_fields_not_overwritten(upgrader):
    """已带 V1 字段的 hypothesis, 升级不覆盖原值 (如 sample_hypothesis 手工标的真值)."""
    hyp = {
        "id": "H-existing",
        "statement": "x 必须 y",
        "source_kind": "spec",
        "source_path": "docs/standards/concepts/worker.md",
        "confidence_level": "medium",          # 已手工标
        "verification_status": "red_green_pass",  # 已手工标
        "related_anti_pattern_ids": ["AP-007"],   # 已手工标
    }
    up = upgrader.upgrade(hyp)
    assert up.upgraded_dict["confidence_level"] == "medium"  # 不被默认 'low' 覆盖
    assert up.upgraded_dict["verification_status"] == "red_green_pass"
    assert up.upgraded_dict["related_anti_pattern_ids"] == ["AP-007"]


# ── 批量统计 ──

def test_batch_distribution(upgrader):
    """批量升级产分布统计."""
    hyps = [
        {"id": "H-a", "source_kind": "code", "source_path": "src/x.py", "statement": "必须 x"},
        {"id": "H-b", "source_kind": "code", "source_path": "src/y.py", "statement": "必须 y"},
        {"id": "H-c", "source_kind": "spec", "source_path": "docs/standards/concepts/worker.md", "statement": "应该 z"},
    ]
    result = upgrader.upgrade_batch(hyps)
    assert len(result.upgraded) == 3
    assert result.by_authority == {"code-derived": 2, "LOW": 1}
    assert result.by_risk == {"high": 2, "medium": 1}


def test_batch_summary_string(upgrader):
    """summary 字符串包含 upgraded/skipped/by_authority/by_risk."""
    hyps = [{"id": "H-x", "source_kind": "code", "source_path": "src/a.py", "statement": "必须 a"}]
    result = upgrader.upgrade_batch(hyps)
    s = result.summary
    assert "upgraded 1" in s
    assert "code-derived" in s
    assert "high" in s


# ── CLI 入口 dogfood (V1 2026-05-07 加) ────────────────────────────────

import yaml as _yaml
from omnicompany.packages.services._diagnosis.doctor.builders.hypothesis_v1_upgrader import (
    main as upgrader_main,
)


def _write_yaml(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        _yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def _read_yaml(path):
    with path.open("r", encoding="utf-8") as f:
        return _yaml.safe_load(f)


@pytest.fixture
def tmp_authority_map(tmp_path):
    """tmp dir 写一份模拟 standards_authority_map.yaml."""
    map_data = {
        "authority_levels": {
            "HIGH": {"documents": [{"path": "docs/standards/_global/standards_meta.md"}]},
            "MEDIUM": {"documents": []},
            "LOW": {"documents": [{"path": "docs/standards/concepts/worker.md"}]},
        }
    }
    map_path = tmp_path / "standards_authority_map.yaml"
    _write_yaml(map_path, map_data)
    return map_path


@pytest.fixture
def tmp_v0_hypotheses(tmp_path):
    """tmp dir 写 V0 假设 yaml 3 份 (含 source_kind=code/spec 各样)."""
    hyp_dir = tmp_path / "hypotheses"
    _write_yaml(hyp_dir / "H-v0-001.yaml", {
        "id": "H-v0-001",
        "source_kind": "code",
        "source_path": "src/old/llm_worker.py",
        "statement": "Worker 必须有 FORMAT_OUT",
        "motivation": "总线契约",
    })
    _write_yaml(hyp_dir / "H-v0-002.yaml", {
        "id": "H-v0-002",
        "source_kind": "spec",
        "source_path": "docs/standards/concepts/worker.md",
        "statement": "应该用 SubmitRouter 提交",
    })
    _write_yaml(hyp_dir / "H-v0-003.yaml", {
        "id": "H-v0-003",
        "source_kind": "code",
        "source_path": "src/old/another_worker.py",
        "statement": "不得在 worker 内调 LLM",
    })
    return hyp_dir


def test_cli_dogfood_dry_run(tmp_authority_map, tmp_v0_hypotheses, capsys):
    """CLI --dry-run 不写盘只看分布."""
    rc = upgrader_main([
        "--hypotheses-dir", str(tmp_v0_hypotheses),
        "--map-path", str(tmp_authority_map),
        "--dry-run",
    ])
    assert rc == 0
    captured = capsys.readouterr()
    assert "upgraded 3" in captured.out
    assert "code-derived" in captured.out
    # 2 个 source_kind=code → code-derived; 1 个 spec source_path 在 LOW 档
    assert "'code-derived': 2" in captured.out or '"code-derived": 2' in captured.out
    assert "'LOW': 1" in captured.out or '"LOW": 1' in captured.out


def test_cli_dogfood_writes_v1_fields_back(tmp_authority_map, tmp_v0_hypotheses, tmp_path):
    """CLI 真跑 (非 dry-run) 写回 V1 字段."""
    out_dir = tmp_path / "upgraded_out"
    rc = upgrader_main([
        "--hypotheses-dir", str(tmp_v0_hypotheses),
        "--map-path", str(tmp_authority_map),
        "--output-dir", str(out_dir),
    ])
    assert rc == 0
    # 验输出 yaml 含 V1 字段
    h001 = _read_yaml(out_dir / "H-v0-001.yaml")
    assert h001["source_authority"] == "code-derived"  # source_kind=code 走 code-derived
    assert h001["risk_if_wrong"] == "high"             # statement 含"必须"
    assert h001["confidence_level"] == "low"
    assert h001["verification_status"] == "untested"
    assert h001["dependent_hypotheses"] == []

    h002 = _read_yaml(out_dir / "H-v0-002.yaml")
    assert h002["source_authority"] == "LOW"  # source_path 在 LOW 档
    assert h002["risk_if_wrong"] == "medium"  # statement 含"应该"

    h003 = _read_yaml(out_dir / "H-v0-003.yaml")
    assert h003["source_authority"] == "code-derived"
    assert h003["risk_if_wrong"] == "high"  # 含"不得"


def test_cli_missing_hypotheses_dir_returns_1(tmp_authority_map, tmp_path):
    """--hypotheses-dir 不存在返 rc=1."""
    rc = upgrader_main([
        "--hypotheses-dir", str(tmp_path / "does_not_exist"),
        "--map-path", str(tmp_authority_map),
    ])
    assert rc == 1


def test_cli_missing_map_returns_2(tmp_v0_hypotheses, tmp_path):
    """--map-path 加载失败返 rc=2."""
    rc = upgrader_main([
        "--hypotheses-dir", str(tmp_v0_hypotheses),
        "--map-path", str(tmp_path / "no_such_map.yaml"),
    ])
    assert rc == 2


def test_cli_empty_dir_returns_0_with_warning(tmp_authority_map, tmp_path, capsys):
    """空目录返 rc=0 + 警告."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    rc = upgrader_main([
        "--hypotheses-dir", str(empty_dir),
        "--map-path", str(tmp_authority_map),
    ])
    assert rc == 0
    captured = capsys.readouterr()
    assert "WARNING" in captured.out
    assert "无 yaml 文件" in captured.out


# ── FindingArchive 反向链接接通 (V1 2026-05-07) ──────────────────────

class _FakeFindingArchive:
    """duck-typed FindingArchive — 测 V1Upgrader 不依赖真 FindingArchive."""

    def __init__(self, mapping: dict[str, list[str]]):
        # mapping: hypothesis_id → [finding_id, ...]
        self.mapping = mapping
        self.calls: list[str] = []

    def find_findings_referencing_hypothesis(self, hid: str) -> list[str]:
        self.calls.append(hid)
        return list(self.mapping.get(hid, []))


def test_v1upgrader_with_archive_fills_related_finding_ids(authority_map):
    """V1Upgrader 传 finding_archive 时反向查填 related_finding_ids."""
    fake = _FakeFindingArchive({
        "H-fa-001": ["F-001", "F-005", "F-100"],
        "H-fa-002": [],  # 没匹
    })
    up = HypothesisV1Upgrader(authority_map=authority_map, finding_archive=fake)

    # H-fa-001 应填 3 个 finding_id
    h1 = up.upgrade({"id": "H-fa-001", "source_kind": "code", "source_path": "x.py", "statement": "必须 x"})
    assert h1.upgraded_dict["related_finding_ids"] == ["F-001", "F-005", "F-100"]
    assert any("FindingArchive 反向查到 3 finding" in n for n in h1.derivation_notes)

    # H-fa-002 没匹, related_finding_ids 应保持空 list (默认值)
    h2 = up.upgrade({"id": "H-fa-002", "source_kind": "code", "source_path": "y.py", "statement": "必须 y"})
    assert h2.upgraded_dict["related_finding_ids"] == []

    # 调过 archive (对每个 hyp 1 次)
    assert fake.calls == ["H-fa-001", "H-fa-002"]


def test_v1upgrader_without_archive_keeps_empty_related_finding_ids(authority_map):
    """不传 finding_archive 时 related_finding_ids 维持默认空 list, 不报错."""
    up = HypothesisV1Upgrader(authority_map=authority_map)
    h = up.upgrade({"id": "H-no-arch", "source_kind": "code", "source_path": "x.py", "statement": "必须 x"})
    assert h.upgraded_dict["related_finding_ids"] == []


def test_v1upgrader_archive_failure_does_not_block_upgrade(authority_map):
    """archive 查询失败 (raise) 不阻塞升级, 只加 note."""

    class _BrokenArchive:
        def find_findings_referencing_hypothesis(self, hid):
            raise RuntimeError("archive 临时挂了")

    up = HypothesisV1Upgrader(authority_map=authority_map, finding_archive=_BrokenArchive())
    h = up.upgrade({"id": "H-broken", "source_kind": "code", "source_path": "x.py", "statement": "必须 x"})
    assert h is not None  # 不抛
    assert h.upgraded_dict["related_finding_ids"] == []
    assert any("FindingArchive 查询失败" in n for n in h.derivation_notes)


def test_v1upgrader_archive_does_not_overwrite_existing_related_finding_ids(authority_map):
    """已带 related_finding_ids 的 hypothesis (例 sample 手工标), archive 反向查的 finding 应当合并不重复."""
    fake = _FakeFindingArchive({"H-existing": ["F-002", "F-003"]})  # archive 查到 F-002, F-003
    up = HypothesisV1Upgrader(authority_map=authority_map, finding_archive=fake)
    h = up.upgrade({
        "id": "H-existing",
        "source_kind": "spec",
        "source_path": "docs/standards/concepts/worker.md",
        "statement": "必须 X",
        "related_finding_ids": ["F-001"],  # 已手工标的
    })
    # 应该合并: ['F-001', 'F-002', 'F-003']
    assert h.upgraded_dict["related_finding_ids"] == ["F-001", "F-002", "F-003"]


def test_v1upgrader_archive_dedupes_with_existing(authority_map):
    """archive 查到的跟已有的有重复 → 不重复加."""
    fake = _FakeFindingArchive({"H-dedup": ["F-001", "F-002"]})
    up = HypothesisV1Upgrader(authority_map=authority_map, finding_archive=fake)
    h = up.upgrade({
        "id": "H-dedup",
        "source_kind": "spec",
        "source_path": "docs/standards/concepts/worker.md",
        "statement": "必须 X",
        "related_finding_ids": ["F-001"],  # F-001 已有
    })
    # 合并后 F-001 不重复
    assert h.upgraded_dict["related_finding_ids"] == ["F-001", "F-002"]


# ── dogfood 历史升级 verification_status (V2 → V1 2026-05-07) ──────────
# 按 schema §三步骤 5: red_green_pass + 实战 ≥3 次 → real_world_validated + confidence=high


def test_red_green_pass_with_3_findings_upgrades_to_real_world_validated(authority_map):
    """red_green_pass + 3 finding → real_world_validated + confidence=high."""
    fake = _FakeFindingArchive({"H-real-001": ["F-001", "F-002", "F-003"]})
    up = HypothesisV1Upgrader(authority_map=authority_map, finding_archive=fake)
    h = up.upgrade({
        "id": "H-real-001",
        "source_kind": "spec",
        "source_path": "docs/standards/concepts/worker.md",
        "statement": "必须 X",
        "verification_status": "red_green_pass",  # 已跑过红绿
        "confidence_level": "medium",
    })
    assert h.upgraded_dict["verification_status"] == "real_world_validated"
    assert h.upgraded_dict["confidence_level"] == "high"
    assert any("real_world_validated" in n for n in h.derivation_notes)


def test_red_green_pass_with_5_findings_upgrades_to_real_world_validated(authority_map):
    """red_green_pass + 5 finding (远超阈值) → real_world_validated."""
    fake = _FakeFindingArchive({"H-real-005": [f"F-{i}" for i in range(5)]})
    up = HypothesisV1Upgrader(authority_map=authority_map, finding_archive=fake)
    h = up.upgrade({
        "id": "H-real-005",
        "source_kind": "code",
        "source_path": "src/x.py",
        "statement": "必须 Y",
        "verification_status": "red_green_pass",
        "confidence_level": "low",  # 即使原 confidence=low 也升 high
    })
    assert h.upgraded_dict["verification_status"] == "real_world_validated"
    assert h.upgraded_dict["confidence_level"] == "high"


def test_red_green_pass_with_2_findings_stays(authority_map):
    """red_green_pass + 2 finding (< 3 阈值) → 维持 red_green_pass, 不升 confidence."""
    fake = _FakeFindingArchive({"H-stay-002": ["F-001", "F-002"]})
    up = HypothesisV1Upgrader(authority_map=authority_map, finding_archive=fake)
    h = up.upgrade({
        "id": "H-stay-002",
        "source_kind": "spec",
        "source_path": "docs/standards/concepts/worker.md",
        "statement": "必须 X",
        "verification_status": "red_green_pass",
        "confidence_level": "medium",
    })
    assert h.upgraded_dict["verification_status"] == "red_green_pass"  # 维持
    assert h.upgraded_dict["confidence_level"] == "medium"             # 不升


def test_red_green_pass_with_no_findings_stays(authority_map):
    """red_green_pass + 0 finding → 维持 red_green_pass."""
    fake = _FakeFindingArchive({})  # archive 没匹
    up = HypothesisV1Upgrader(authority_map=authority_map, finding_archive=fake)
    h = up.upgrade({
        "id": "H-no-finding",
        "source_kind": "spec",
        "source_path": "docs/standards/concepts/worker.md",
        "statement": "必须 X",
        "verification_status": "red_green_pass",
        "confidence_level": "medium",
    })
    assert h.upgraded_dict["verification_status"] == "red_green_pass"


def test_untested_with_5_findings_does_not_jump_to_real_world(authority_map):
    """untested + 5 finding → 维持 untested (不能从 untested 直接跳 real_world_validated, 必须先红绿).

    schema §三步骤 5: red_green_pass + 实战 ≥3 → real_world_validated.
    untested 没跑过红绿, 即便 finding 多也只能维持 untested.
    """
    fake = _FakeFindingArchive({"H-untested": [f"F-{i}" for i in range(5)]})
    up = HypothesisV1Upgrader(authority_map=authority_map, finding_archive=fake)
    h = up.upgrade({
        "id": "H-untested",
        "source_kind": "spec",
        "source_path": "docs/standards/concepts/worker.md",
        "statement": "必须 X",
        # verification_status 未带 → 默认 'untested'
    })
    assert h.upgraded_dict["verification_status"] == "untested"
    assert h.upgraded_dict["confidence_level"] == "low"


def test_falsified_with_findings_stays_falsified(authority_map):
    """status=falsified + finding → 维持 falsified (已被证否的不该被实战 finding 翻案)."""
    fake = _FakeFindingArchive({"H-falsified": [f"F-{i}" for i in range(5)]})
    up = HypothesisV1Upgrader(authority_map=authority_map, finding_archive=fake)
    h = up.upgrade({
        "id": "H-falsified",
        "source_kind": "spec",
        "source_path": "docs/standards/concepts/worker.md",
        "statement": "必须 X",
        "verification_status": "falsified",
        "confidence_level": "low",
    })
    assert h.upgraded_dict["verification_status"] == "falsified"
    assert h.upgraded_dict["confidence_level"] == "low"


# ── V5.2: CLI 默认接通 FindingArchive (2026-05-07) ──────────────────────

def test_cli_default_uses_finding_archive(tmp_authority_map, tmp_v0_hypotheses, tmp_path, monkeypatch):
    """V5.2: CLI 默认接通 FindingArchive — related_finding_ids 真自动填."""
    # patch get_finding_archive 返 fake archive 含已知映射
    fake_finding_ids = ["F-fake-001", "F-fake-002"]

    class _FakeArchive:
        def find_findings_referencing_hypothesis(self, hid):
            if hid == "H-v0-001":
                return list(fake_finding_ids)
            return []

    def _fake_get_archive():
        return _FakeArchive()

    from omnicompany.packages.services._core.registry import finding_archive as fa_module
    monkeypatch.setattr(fa_module, "get_finding_archive", _fake_get_archive)

    out_dir = tmp_path / "out_v52"
    rc = upgrader_main([
        "--hypotheses-dir", str(tmp_v0_hypotheses),
        "--map-path", str(tmp_authority_map),
        "--output-dir", str(out_dir),
        # 不传 --no-finding-archive → 默认接通
    ])
    assert rc == 0
    h001 = _read_yaml(out_dir / "H-v0-001.yaml")
    assert h001["related_finding_ids"] == fake_finding_ids


def test_cli_no_finding_archive_skips_backref(tmp_authority_map, tmp_v0_hypotheses, tmp_path, monkeypatch):
    """--no-finding-archive 跳过反向链接, related_finding_ids 维持空."""

    class _FakeArchive:
        def find_findings_referencing_hypothesis(self, hid):
            return ["F-should-not-appear"]

    from omnicompany.packages.services._core.registry import finding_archive as fa_module
    monkeypatch.setattr(fa_module, "get_finding_archive", lambda: _FakeArchive())

    out_dir = tmp_path / "out_no_archive"
    rc = upgrader_main([
        "--hypotheses-dir", str(tmp_v0_hypotheses),
        "--map-path", str(tmp_authority_map),
        "--output-dir", str(out_dir),
        "--no-finding-archive",
    ])
    assert rc == 0
    h001 = _read_yaml(out_dir / "H-v0-001.yaml")
    # 没接通 archive → related_finding_ids 应是默认空 list
    assert h001["related_finding_ids"] == []


def test_cli_archive_load_failure_does_not_block(tmp_authority_map, tmp_v0_hypotheses, tmp_path, monkeypatch, capsys):
    """archive 加载失败不阻塞 CLI 主路径."""

    def _broken_get_archive():
        raise RuntimeError("archive 临时挂了")

    from omnicompany.packages.services._core.registry import finding_archive as fa_module
    monkeypatch.setattr(fa_module, "get_finding_archive", _broken_get_archive)

    out_dir = tmp_path / "out_broken"
    rc = upgrader_main([
        "--hypotheses-dir", str(tmp_v0_hypotheses),
        "--map-path", str(tmp_authority_map),
        "--output-dir", str(out_dir),
    ])
    assert rc == 0  # 不阻塞
    captured = capsys.readouterr()
    assert "FindingArchive 加载失败" in captured.err
    # 升级仍写盘
    h001 = _read_yaml(out_dir / "H-v0-001.yaml")
    assert h001["related_finding_ids"] == []


def test_cli_idempotent_v1_fields(tmp_authority_map, tmp_path):
    """已带 V1 字段的 yaml 重跑不覆盖 (sample_hypothesis 真值场景)."""
    hyp_dir = tmp_path / "v1_already"
    _write_yaml(hyp_dir / "H-already.yaml", {
        "id": "H-already",
        "source_kind": "spec",
        "source_path": "docs/standards/concepts/worker.md",
        "statement": "Worker 必须有 FORMAT_OUT",
        "confidence_level": "medium",          # 已手工标
        "verification_status": "red_green_pass",  # 已手工标
        "related_anti_pattern_ids": ["AP-007"],
    })
    out_dir = tmp_path / "out_idem"
    rc = upgrader_main([
        "--hypotheses-dir", str(hyp_dir),
        "--map-path", str(tmp_authority_map),
        "--output-dir", str(out_dir),
    ])
    assert rc == 0
    out = _read_yaml(out_dir / "H-already.yaml")
    assert out["confidence_level"] == "medium"
    assert out["verification_status"] == "red_green_pass"
    assert out["related_anti_pattern_ids"] == ["AP-007"]
    # 但 source_authority 字段如果 V0 没标, V1 派生填上
    assert out["source_authority"] == "LOW"
