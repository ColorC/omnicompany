"""材料统一阶段 0 — 公司级材料 Format 字典的契约测试。"""
from omnicompany.packages.services._core.omnicompany.formats import (
    FORMATS,
    register_formats,
)
from omnicompany.protocol.format import create_builtin_registry


def test_register_into_builtin_registry():
    registry = create_builtin_registry()
    register_formats(registry)
    for fmt in FORMATS:
        assert registry.is_registered(fmt.id), fmt.id


def test_ids_unique_and_namespaced():
    ids = [f.id for f in FORMATS]
    assert len(ids) == len(set(ids))
    assert all(i.startswith("omni.") for i in ids)


def test_all_carry_material_tag():
    assert all("omni.material" in f.tags for f in FORMATS)


def test_register_idempotent():
    registry = create_builtin_registry()
    register_formats(registry)
    register_formats(registry)  # 二次注册不应抛重复 id
    assert registry.is_registered("omni.review-material")
