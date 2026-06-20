# [OMNI] origin=human ts=2026-04-08T03:23:35Z
# [OMNI] material_id="material:cli.db_helpers.connection_and_formatting.utils.py"
"""CLI 共享工具：DB 连接、格式化辅助。"""
import os
import sqlite3
import json
from pathlib import Path

DEFAULT_DB = os.environ.get(
    "OMNI_DB",
    str(Path(__file__).resolve().parents[3] / "data" / "autonomous" / "semantic_network.db"),
)


def open_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def resolve_db(db_option: str | None) -> str:
    return db_option or DEFAULT_DB


def fmt_time(ts: float | None) -> str:
    if not ts:
        return "-"
    import datetime
    return datetime.datetime.fromtimestamp(ts).strftime("%m-%d %H:%M")


def fmt_bool(v: int | None, true_str="ok", false_str="FAIL") -> str:
    if v is None:
        return "?"
    return true_str if v else false_str


def truncate(s: str | None, n: int = 80) -> str:
    if not s:
        return "-"
    s = s.replace("\n", " ")
    return s[:n] + "..." if len(s) > n else s


def type_ids(json_str: str | None) -> str:
    if not json_str:
        return "-"
    try:
        items = json.loads(json_str)
        return ", ".join(t.get("type_id", str(t)) for t in items)
    except Exception:
        return json_str or "-"


def parse_json_list(s: str | None) -> list:
    if not s:
        return []
    try:
        return json.loads(s)
    except Exception:
        return []
