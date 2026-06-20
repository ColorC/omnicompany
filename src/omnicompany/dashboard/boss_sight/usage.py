# [OMNI] origin=ai-ide ts=2026-06-07 type=infra
# [OMNI] material_id="material:dashboard.boss_sight.usage_meter.py"
"""usage — Claude **官方剩余配额**, 直接读 Anthropic OAuth usage 端点。

用户 2026-06-07: "不要本地估! 我要官方的百分比, 直接读官方的" + "有不少开源插件...完全照抄就行"。
照抄社区事实标准 github.com/ohugonnot/claude-code-statusline 的做法:
用 `claude login` 存在 ~/.claude/.credentials.json 的 OAuth token 直接打官方端点
  GET https://api.anthropic.com/api/oauth/usage
      Authorization: Bearer <claudeAiOauth.accessToken>
      anthropic-beta: oauth-2025-04-20
返回各窗口 `{utilization(已用%), resets_at(ISO)}`: five_hour / seven_day / seven_day_opus /
seven_day_sonnet。**剩余% = 100 - utilization**。这是 Anthropic 官方数字(非本地日志估算)。

Codex: codex CLI 每轮把官方限额写进会话日志 ~/.codex/sessions/**/*.jsonl 的 `rate_limits`
(primary=5h 窗口、secondary=周窗口, 各带 used_percent + resets_at epoch) —— 这就是 `/status`
显示的同一份官方数据, 直接读最近日志最后一条即可, 不必驱动 TUI 模拟输入。剩余% = 100 - used_percent。
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_TTL = 300.0  # 官方 oauth/usage 限流敏感, 5 分钟缓存(配额%变化慢, 没必要勤拉)
_CACHE: dict[str, Any] = {"ts": 0.0, "data": None}
# 上次成功读到的值(按 provider), 临时失败(429/网络)时回退展示而非报错盖掉。
_LAST_GOOD: dict[str, dict[str, Any]] = {}
# 被 429 限流后的冷却: 这段时间内不再打官方端点, 直接回退 last-good。
_CLAUDE_COOLDOWN_UNTIL = 0.0
_CLAUDE_429_COOLDOWN = 600.0  # 命中 429 后冷却 10 分钟(不再打端点, 给它恢复)

_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
_CREDENTIALS = Path.home() / ".claude" / ".credentials.json"

# last-good 落盘, 让 ccdaemon 重启后遇 429 仍能显示上次读数(而非空着报错)。
try:
    from omnicompany.core.config import omni_workspace_root as _ws_root
    _LAST_GOOD_FILE: Path | None = _ws_root() / "data" / "boss_sight" / "usage_last_good.json"
except Exception:  # noqa: BLE001
    _LAST_GOOD_FILE = None


def _load_last_good() -> None:
    if not _LAST_GOOD_FILE:
        return
    try:
        d = json.loads(_LAST_GOOD_FILE.read_text(encoding="utf-8"))
        if isinstance(d, dict):
            _LAST_GOOD.update({k: v for k, v in d.items() if isinstance(v, dict)})
    except (OSError, json.JSONDecodeError):
        pass


def _save_last_good() -> None:
    if not _LAST_GOOD_FILE:
        return
    try:
        _LAST_GOOD_FILE.parent.mkdir(parents=True, exist_ok=True)
        _LAST_GOOD_FILE.write_text(json.dumps(_LAST_GOOD, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


_load_last_good()  # 进程启动即载入上次读数, 重启后遇 429 也能显示


def _oauth_token() -> str | None:
    """读 claude login 存的 OAuth access token(同 claude-code-statusline)。"""
    try:
        d = json.loads(_CREDENTIALS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return (d.get("claudeAiOauth") or {}).get("accessToken") or None


def _fetch_official() -> dict[str, Any]:
    token = _oauth_token()
    if not token:
        raise RuntimeError(f"未找到 claude OAuth token({_CREDENTIALS}); 先 `claude login`")
    req = urllib.request.Request(  # noqa: S310 - 官方 anthropic 端点, 固定 URL
        _USAGE_URL,
        headers={"Authorization": f"Bearer {token}", "anthropic-beta": "oauth-2025-04-20"},
    )
    with urllib.request.urlopen(req, timeout=8) as r:  # noqa: S310
        return json.loads(r.read().decode())


def _reset_in_sec(resets_at: Any) -> int | None:
    """resets_at → 距现在还有多少秒。兼容 Claude 的 ISO 8601 与 codex 的 epoch 秒。
    过去/解析失败 → None。"""
    if resets_at is None or resets_at == "":
        return None
    try:
        if isinstance(resets_at, (int, float)):
            delta = float(resets_at) - time.time()
        else:
            dt = datetime.fromisoformat(str(resets_at))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            delta = dt.timestamp() - time.time()
    except (ValueError, TypeError):
        return None
    return int(delta) if delta > 0 else 0


def _window(d: dict[str, Any], key: str) -> dict[str, Any] | None:
    """把官方某窗口转成 {已用%, 剩余%, resets_at, reset_in_sec}。"""
    w = d.get(key)
    if not isinstance(w, dict) or w.get("utilization") is None:
        return None
    util = float(w.get("utilization") or 0.0)
    return {
        "used_pct": round(util, 1),
        "remaining_pct": round(max(0.0, 100.0 - util), 1),
        "resets_at": w.get("resets_at"),
        "reset_in_sec": _reset_in_sec(w.get("resets_at")),
    }


def _claude() -> dict[str, Any]:
    global _CLAUDE_COOLDOWN_UNTIL
    now = time.time()
    last = _LAST_GOOD.get("claude")
    # 429 冷却期内不再打端点(给它恢复时间): 有上次读数就回退展示, 没有就给干净的"冷却中"提示。
    if now < _CLAUDE_COOLDOWN_UNTIL:
        if last:
            return {**last, "stale": True, "stale_reason": "官方端点限流(429)冷却中, 显示上次读数"}
        return {"available": False, "reason": "官方 usage 端点暂被限流(429), 冷却中, 稍后自动恢复"}
    try:
        d = _fetch_official()
    except Exception as e:  # noqa: BLE001
        is_429 = isinstance(e, urllib.error.HTTPError) and getattr(e, "code", None) == 429
        if is_429:
            _CLAUDE_COOLDOWN_UNTIL = now + _CLAUDE_429_COOLDOWN
        if last:  # 临时失败优先回退上次成功值, 别用错误盖掉好数据
            why = "官方端点限流(429)" if is_429 else type(e).__name__
            return {**last, "stale": True, "stale_reason": f"{why}, 显示上次读数"}
        if is_429:
            return {"available": False, "reason": "官方 usage 端点暂被限流(429), 稍后自动恢复"}
        return {"available": False, "reason": f"读官方 usage 失败: {type(e).__name__}: {str(e)[:80]}"}
    out: dict[str, Any] = {"available": True}
    for key in ("five_hour", "seven_day", "seven_day_opus", "seven_day_sonnet"):
        w = _window(d, key)
        if w is not None:
            out[key] = w
    if len(out) == 1:  # 只有 available, 一个窗口都没解析出
        if last:
            return {**last, "stale": True, "stale_reason": "官方端点返回无可识别窗口, 显示上次读数"}
        return {"available": False, "reason": "官方端点返回里没有可识别的配额窗口"}
    _LAST_GOOD["claude"] = out
    _CLAUDE_COOLDOWN_UNTIL = 0.0  # 成功即清冷却
    _save_last_good()
    return out


_CODEX_SESSIONS = Path.home() / ".codex" / "sessions"


def _codex_window(w: Any) -> dict[str, Any] | None:
    """codex rate_limits 的 primary/secondary → 统一窗口结构(used_percent + epoch resets_at)。"""
    if not isinstance(w, dict) or w.get("used_percent") is None:
        return None
    used = float(w.get("used_percent") or 0.0)
    return {
        "used_pct": round(used, 1),
        "remaining_pct": round(max(0.0, 100.0 - used), 1),
        "resets_at": w.get("resets_at"),
        "reset_in_sec": _reset_in_sec(w.get("resets_at")),
        "window_minutes": w.get("window_minutes"),
    }


def _codex_last_rate_limits() -> dict[str, Any] | None:
    """读最近 codex 会话日志里最后一条 rate_limits(codex 每轮把官方限额写进 rollout jsonl)。

    这就是 codex `/status` 显示的同一份官方数据 —— 不用驱动 TUI 模拟输入。大文件只读尾部。
    """
    try:
        logs = sorted(
            _CODEX_SESSIONS.glob("**/*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True
        )
    except OSError:
        return None
    for lg in logs[:5]:
        try:
            size = lg.stat().st_size
            with lg.open("rb") as f:
                if size > 1_000_000:  # 大日志只读尾部 1MB
                    f.seek(size - 1_000_000)
                    f.readline()  # 丢弃可能被截断的半行
                text = f.read().decode("utf-8", errors="ignore")
        except OSError:
            continue
        last_line = None
        for line in text.splitlines():
            if '"rate_limits"' in line:
                last_line = line
        if not last_line:
            continue
        try:
            obj = json.loads(last_line)
        except json.JSONDecodeError:
            continue
        rl = _deep_find_key(obj, "rate_limits")
        if rl:
            return rl
    return None


def _deep_find_key(d: Any, key: str) -> Any:
    if isinstance(d, dict):
        if key in d and d[key]:
            return d[key]
        for v in d.values():
            r = _deep_find_key(v, key)
            if r is not None:
                return r
    elif isinstance(d, list):
        for v in d:
            r = _deep_find_key(v, key)
            if r is not None:
                return r
    return None


def _codex() -> dict[str, Any]:
    """codex 官方剩余: 读 ~/.codex/sessions 最近日志里最后一条 rate_limits(同 /status 数据源)。"""
    last = _LAST_GOOD.get("codex")
    rl = _codex_last_rate_limits()
    if not rl:
        if last:
            return {**last, "stale": True, "stale_reason": "暂未读到 codex 限额日志, 显示上次读数"}
        return {"available": False, "reason": "未找到 codex 限额日志(~/.codex/sessions; 先用 codex 跑一轮)"}
    out: dict[str, Any] = {"available": True, "plan_type": rl.get("plan_type")}
    five = _codex_window(rl.get("primary"))  # primary=5h 窗口(window_minutes≈300)
    week = _codex_window(rl.get("secondary"))  # secondary=周窗口(window_minutes≈10080)
    if five:
        out["five_hour"] = five
    if week:
        out["seven_day"] = week
    if "five_hour" not in out and "seven_day" not in out:
        if last:
            return {**last, "stale": True, "stale_reason": "codex 日志无可识别窗口, 显示上次读数"}
        return {"available": False, "reason": "codex 日志里无可识别的限额窗口"}
    _LAST_GOOD["codex"] = out
    _save_last_good()
    return out


def build_usage(force: bool = False) -> dict[str, Any]:
    """Claude 官方剩余配额(直接读 Anthropic oauth/usage 端点)。60s 缓存。"""
    now = time.time()
    if not force and _CACHE["data"] is not None and (now - _CACHE["ts"]) < _TTL:
        return _CACHE["data"]
    data = {
        "generated_at": now,
        "source": "Anthropic 官方 oauth/usage 端点",
        "claude": _claude(),
        "codex": _codex(),
        "note": "官方剩余配额(100-已用%): Claude 读 oauth/usage 端点, Codex 读 ~/.codex 会话日志 rate_limits(同 /status)。",
    }
    _CACHE["data"] = data
    _CACHE["ts"] = now
    return data


__all__ = ["build_usage"]
