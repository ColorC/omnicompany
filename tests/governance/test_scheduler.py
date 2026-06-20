"""治理定时 runner 的到期判定测试(不跑真命令、不动真 .omni/cron)。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from omnicompany.packages.services._governance.scheduler import _cadence_seconds, is_due


def test_cadence_presets():
    assert _cadence_seconds("@daily") == 86400
    assert _cadence_seconds("@weekly") == 604800
    assert _cadence_seconds("@hourly") == 3600
    assert _cadence_seconds("0 3 * * *") == 86400  # 原始 cron 保守按每日


def test_never_run_is_due():
    assert is_due({"schedule": "@daily", "last_run_at": None})
    assert is_due({"schedule": "@daily"})  # 缺字段也算到期


def test_due_after_interval():
    now = datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc)
    just_ran = (now - timedelta(hours=2)).isoformat()
    long_ago = (now - timedelta(days=2)).isoformat()
    # 每日任务: 2 小时前跑过 → 未到期; 2 天前 → 到期
    assert not is_due({"schedule": "@daily", "last_run_at": just_ran}, now=now)
    assert is_due({"schedule": "@daily", "last_run_at": long_ago}, now=now)
    # 每周任务: 2 天前跑过 → 未到期
    assert not is_due({"schedule": "@weekly", "last_run_at": long_ago}, now=now)


def test_naive_timestamp_treated_as_utc():
    now = datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc)
    naive = "2026-06-13T11:00:00"  # 1 小时前, 无时区
    assert not is_due({"schedule": "@daily", "last_run_at": naive}, now=now)
