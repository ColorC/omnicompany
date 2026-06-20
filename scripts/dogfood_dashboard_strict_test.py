# OMNI-PERSISTENT-SCRIPT owner=dashboard purpose=chat-interface-e2e-smoke
#!/usr/bin/env python3
# [OMNI] origin=ai-ide ts=2026-05-09 type=test
# [OMNI] material_id="material:scripts.dogfood_dashboard_strict_test.real_chat_e2e.py"
"""dogfood 严密测试 — 真 chat session 端到端 + 故障注入.

跟 dogfood_dashboard_resilience_test.py 互补:
  resilience_test.py  echo + health 验通信层 (快, 不烧 token)
  strict_test.py      真起 chat session, 真发 prompt, 真验跨 reload 续展 (慢, 烧少量 token)

跑前提:
- 本机装了 claude binary (PATH 上有 `claude`) + 已 `claude login` (Claude Max 订阅)
- 没装 / 没登: 测试 SKIP 而不是 FAIL

场景
----
S1 setup            两进程起, /api/cc/chat/health 经反向代理 200
S2 chat_one_turn    创 chat session, 发 "echo back the word PING-9527", 等 assistant
                    含 "PING-9527", 验 history_summary 落盘
S3 reload_continuity chat 跑中触发 dashboard reload, 重连 ws, snapshot 帧含上一轮
                    user/assistant 历史; 续发新 prompt 再跑一回合
S4 daemon_kill9     kill -9 daemon → 浏览器 ws close (1011 / 异常断), 拉起新 daemon →
                    新 ws 创建后 (老 session 元数据已恢复) snapshot 行为符合 §6.5 预期
S5 multi_session    并发 3 个 chat session, 改 controlplane 触发 dashboard reload,
                    三个 ws 都重连成功, 三个 session 元数据都在
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

try:
    from websockets.sync.client import connect as ws_connect
except ImportError:
    print("FATAL: websockets >= 12 needed", file=sys.stderr)
    sys.exit(2)


REPO_ROOT = Path(__file__).resolve().parent.parent
DAEMON_PORT = int(os.environ.get("OMNI_STRICT_DAEMON_PORT", "8231"))
DASHBOARD_PORT = int(os.environ.get("OMNI_STRICT_DASHBOARD_PORT", "8230"))
DASHBOARD = f"http://127.0.0.1:{DASHBOARD_PORT}"
DAEMON = f"http://127.0.0.1:{DAEMON_PORT}"

# Per-turn LLM 等待上限 — 真 claude (sonnet/haiku) 简单 prompt 通常 5-15s, 给充裕
PROMPT_TIMEOUT_S = 60.0

results: list[tuple[str, str, str]] = []


def http_get(url: str, timeout: float = 5.0) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read() if e.fp else b""
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        return 0, str(e).encode()


def http_post_json(url: str, body: dict | None = None, timeout: float = 10.0) -> tuple[int, bytes]:
    data = json.dumps(body or {}).encode() if body is not None else b"{}"
    req = urllib.request.Request(url, data=data, method="POST",
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read() if e.fp else b""
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        return 0, str(e).encode()


def http_delete(url: str, timeout: float = 5.0) -> tuple[int, bytes]:
    req = urllib.request.Request(url, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read() if e.fp else b""
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        return 0, str(e).encode()


def wait_until(check: Callable[[], bool], timeout_s: float, interval_s: float = 0.3) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if check():
            return True
        time.sleep(interval_s)
    return False


def record(name: str, status: str, note: str = "") -> None:
    results.append((name, status, note))
    color = {"PASS": "\033[32m", "FAIL": "\033[31m", "SKIP": "\033[33m"}.get(status, "")
    reset = "\033[0m" if color else ""
    print(f"  [{color}{status}{reset}] {name}{(' — ' + note) if note else ''}")


def claude_available() -> bool:
    return shutil.which("claude") is not None or shutil.which("claude.cmd") is not None


def spawn_daemon() -> subprocess.Popen:
    env = os.environ.copy()
    env["OMNI_CC_DAEMON_PORT"] = str(DAEMON_PORT)
    flags = 0x00000200 if sys.platform == "win32" else 0  # CREATE_NEW_PROCESS_GROUP
    log = REPO_ROOT / "data" / "strict_daemon.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log_fd = open(log, "ab")
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn",
         "omnicompany.dashboard.ccdaemon.main:app",
         "--host", "127.0.0.1", "--port", str(DAEMON_PORT),
         "--log-level", "warning"],
        cwd=str(REPO_ROOT), env=env, creationflags=flags,
        stdout=log_fd, stderr=subprocess.STDOUT,
    )


def spawn_dashboard() -> subprocess.Popen:
    log = REPO_ROOT / "data" / "strict_dashboard.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log_fd = open(log, "ab")
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn",
         "omnicompany.dashboard.app:app",
         "--host", "127.0.0.1", "--port", str(DASHBOARD_PORT),
         "--reload",
         "--reload-dir", str(REPO_ROOT / "src" / "omnicompany" / "dashboard"),
         "--reload-exclude", "src/omnicompany/dashboard/ccdaemon",
         "--log-level", "warning"],
        cwd=str(REPO_ROOT),
        stdout=log_fd, stderr=subprocess.STDOUT,
    )


def kill_proc(p: subprocess.Popen | None, force: bool = False) -> None:
    if p is None:
        return
    try:
        if force or sys.platform == "win32":
            p.kill()
        else:
            p.send_signal(signal.SIGTERM)
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                p.kill()
    except Exception:
        pass


def collect_assistant_text(ws, *, deadline_s: float) -> tuple[str, bool]:
    """读 ws frames 直到 ResultMessage; 收齐 assistant text content. 返回 (text, ok)."""
    end = time.time() + deadline_s
    text_chunks: list[str] = []
    got_result = False
    while time.time() < end:
        remaining = end - time.time()
        if remaining <= 0:
            break
        try:
            raw = ws.recv(timeout=min(remaining, 30.0))
        except TimeoutError:
            continue
        if not raw:
            continue
        try:
            frame = json.loads(raw)
        except json.JSONDecodeError:
            continue
        kind = frame.get("kind")
        if kind == "assistant":
            for b in frame.get("content", []):
                if isinstance(b, dict) and b.get("type") == "text":
                    text_chunks.append(b.get("text", ""))
        elif kind == "result":
            got_result = True
            break
        elif kind == "error":
            return ("ERROR: " + str(frame), False)
    return ("".join(text_chunks), got_result)


def consume_until_kind(ws, target_kinds: set[str], *, timeout_s: float) -> dict | None:
    end = time.time() + timeout_s
    while time.time() < end:
        try:
            raw = ws.recv(timeout=min(end - time.time(), 5.0))
        except TimeoutError:
            continue
        try:
            frame = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if frame.get("kind") in target_kinds:
            return frame
    return None


def run() -> int:
    print(f"[setup] daemon=:{DAEMON_PORT}  dashboard=:{DASHBOARD_PORT}")

    # 清陈旧 pid (避免 lifecycle 误判)
    subprocess.run([sys.executable, "-m", "omnicompany.cli.main", "cc", "daemon", "stop"],
                   cwd=str(REPO_ROOT), capture_output=True)

    if not claude_available():
        print("[skip] claude binary not on PATH; skipping all chat scenarios.")
        record("env.claude_binary", "SKIP", "claude CLI not installed/on PATH")
        return 0

    daemon_proc: subprocess.Popen | None = None
    dashboard_proc: subprocess.Popen | None = None
    created_session_ids: list[str] = []

    try:
        # ── S1 · setup ──────────────────────────────────────────────────────
        print("\n[S1/5] setup: daemon + dashboard up, /api/cc/chat/health proxied")
        daemon_proc = spawn_daemon()
        if not wait_until(lambda: http_get(f"{DAEMON}/health")[0] == 200, 25):
            record("S1.daemon_ready", "FAIL", "daemon /health timeout 25s")
            return 1
        record("S1.daemon_ready", "PASS")

        dashboard_proc = spawn_dashboard()
        if not wait_until(lambda: http_get(f"{DASHBOARD}/api/cc/chat/health")[0] == 200, 45):
            record("S1.dashboard_chat_health", "FAIL", "/api/cc/chat/health timeout 45s")
            return 1
        record("S1.dashboard_chat_health", "PASS")

        # ── S2 · chat_one_turn ──────────────────────────────────────────────
        print("\n[S2/5] chat_one_turn: create session, send prompt, recv assistant")
        # POST /api/cc/chat/sessions (走反向代理 → daemon /cc/chat/sessions)
        # body: cwd / model 默认即可
        code, body = http_post_json(f"{DASHBOARD}/api/cc/chat/sessions", {})
        if code != 200:
            record("S2.create_session", "FAIL", f"POST /api/cc/chat/sessions {code} body={body[:200]!r}")
            return 1
        meta = json.loads(body)
        sid = meta["id"]
        created_session_ids.append(sid)
        record("S2.create_session", "PASS", f"sid={sid} model={meta.get('model')}")

        ws_url = f"ws://127.0.0.1:{DASHBOARD_PORT}/api/cc/chat/sessions/{sid}/ws"
        try:
            with ws_connect(ws_url, open_timeout=10) as ws:
                # 第一帧应是 snapshot (history 空)
                first = ws.recv(timeout=5)
                first_frame = json.loads(first)
                if first_frame.get("kind") != "snapshot":
                    record("S2.snapshot_frame", "FAIL",
                           f"first frame not snapshot: {first_frame.get('kind')}")
                    return 1
                if first_frame.get("history"):
                    record("S2.snapshot_empty", "FAIL",
                           f"new session snapshot history not empty: {first_frame['history']}")
                else:
                    record("S2.snapshot_empty", "PASS")

                # 发 prompt — magic word "PING-9527" 让 assistant 回里包含, 用来验证响应是真的
                magic = "PING-9527"
                prompt = f"Echo back exactly the word {magic} and nothing else."
                ws.send(json.dumps({"type": "user.message", "content": prompt}))

                text, ok = collect_assistant_text(ws, deadline_s=PROMPT_TIMEOUT_S)
                if not ok:
                    record("S2.assistant_response", "FAIL",
                           f"no result frame after {PROMPT_TIMEOUT_S}s; partial text={text[:200]!r}")
                    return 1
                if magic not in text:
                    record("S2.assistant_response", "FAIL",
                           f"assistant text does not contain '{magic}': got {text[:200]!r}")
                    return 1
                record("S2.assistant_response", "PASS",
                       f"assistant returned magic '{magic}' (text len={len(text)})")
        except Exception as e:
            record("S2.ws_chat", "FAIL", f"{type(e).__name__}: {e}")
            return 1

        # 验 history_summary 落盘
        sessions_json = REPO_ROOT / "data" / "cc_sessions.json"
        if sessions_json.is_file():
            try:
                store = json.loads(sessions_json.read_text(encoding="utf-8"))
                entry = store.get(sid, {})
                # to_meta 只挂 buffered_chunks (= len(history_summary))
                bc = entry.get("buffered_chunks", 0)
                if bc >= 2:  # at least 1 user + 1 assistant
                    record("S2.history_persisted", "PASS",
                           f"buffered_chunks={bc} in cc_sessions.json")
                else:
                    record("S2.history_persisted", "FAIL",
                           f"buffered_chunks={bc} (expected ≥ 2)")
            except Exception as e:
                record("S2.history_persisted", "FAIL", f"read sessions json: {e}")
        else:
            record("S2.history_persisted", "SKIP", "cc_sessions.json not present")

        # ── S3 · reload_continuity ─────────────────────────────────────────
        print("\n[S3/5] reload_continuity: trigger dashboard reload, ws reconnect, snapshot has history")
        target = REPO_ROOT / "src" / "omnicompany" / "dashboard" / "controlplane" / "notes.py"
        target.touch()
        time.sleep(5)  # 等 uvicorn reload 完
        # 重新连 ws
        try:
            with ws_connect(ws_url, open_timeout=10) as ws2:
                snap = ws2.recv(timeout=5)
                snap_frame = json.loads(snap)
                if snap_frame.get("kind") != "snapshot":
                    record("S3.reconnect_snapshot_kind", "FAIL",
                           f"first frame after reload not snapshot: {snap_frame.get('kind')}")
                else:
                    history = snap_frame.get("history", [])
                    has_user = any(h.get("role") == "user" and "PING-9527" in (h.get("text") or "")
                                   for h in history)
                    has_assistant = any(h.get("role") == "assistant" and "PING-9527" in (h.get("text") or "")
                                        for h in history)
                    if has_user and has_assistant:
                        record("S3.reconnect_history_intact", "PASS",
                               f"history={len(history)} entries, magic word survived dashboard reload")
                    else:
                        record("S3.reconnect_history_intact", "FAIL",
                               f"history missing magic; user_match={has_user} assistant_match={has_assistant}")
                # 再发一轮看 daemon 真 SDK client 还活
                ws2.send(json.dumps({"type": "user.message",
                                     "content": "Reply with exactly: ROUND2-OK"}))
                text, ok = collect_assistant_text(ws2, deadline_s=PROMPT_TIMEOUT_S)
                if ok and "ROUND2-OK" in text:
                    record("S3.continued_chat", "PASS", "second turn completed cleanly")
                else:
                    record("S3.continued_chat", "FAIL",
                           f"second turn ok={ok} text={text[:200]!r}")
        except Exception as e:
            record("S3.reload_continuity", "FAIL", f"{type(e).__name__}: {e}")

        # ── S4 · multi_session (先做, 因为这要 daemon 还活着, in-memory session 保留) ──
        print("\n[S4/5] multi_session: 3 concurrent chat sessions survive dashboard reload")
        sids = [sid]  # 已有 1 个 (S2/S3 创的); 再造 2 个
        try:
            for i in range(2):
                code, body = http_post_json(f"{DASHBOARD}/api/cc/chat/sessions", {})
                if code == 200:
                    new_sid = json.loads(body)["id"]
                    sids.append(new_sid)
                    created_session_ids.append(new_sid)
            if len(sids) != 3:
                record("S4.create_3_sessions", "FAIL", f"only got {len(sids)} sessions (need 3)")
            else:
                record("S4.create_3_sessions", "PASS", f"sids={sids}")
                # 触发 dashboard reload (daemon 不动, 三个 in-memory session 保留)
                target.touch()
                time.sleep(5)
                ok_count = 0
                for s in sids:
                    try:
                        url = f"ws://127.0.0.1:{DASHBOARD_PORT}/api/cc/chat/sessions/{s}/ws"
                        with ws_connect(url, open_timeout=8) as ws:
                            snap = ws.recv(timeout=5)
                            if json.loads(snap).get("kind") == "snapshot":
                                ok_count += 1
                    except Exception as e:
                        print(f"    reconnect failed for {s}: {e}", file=sys.stderr)
                if ok_count == 3:
                    record("S4.three_reconnect", "PASS",
                           "all 3 sessions snapshot-reconnected after dashboard reload")
                else:
                    record("S4.three_reconnect", "FAIL", f"{ok_count}/3 reconnected")
        except Exception as e:
            record("S4.multi_session", "FAIL", f"{type(e).__name__}: {e}")

        from omnicompany.dashboard.ccdaemon import lifecycle
        before = lifecycle.read_status()
        if not (before.alive and before.pid):
            record("S5.precondition", "SKIP", "daemon not alive at S5 start")
        else:
            kill_proc(daemon_proc, force=True)
            daemon_proc = None
            time.sleep(2)
            code, body = http_get(f"{DASHBOARD}/api/cc/health", timeout=5)
            if code == 503:
                record("S5.proxy_returns_503", "PASS", f"503 with body={body[:120]!r}")
            else:
                record("S5.proxy_returns_503", "FAIL",
                       f"expected 503 after daemon kill, got {code}")
            # 拉起新 daemon
            daemon_proc = spawn_daemon()
            if wait_until(lambda: http_get(f"{DAEMON}/health")[0] == 200, 25):
                code, _ = http_get(f"{DASHBOARD}/api/cc/health", timeout=5)
                if code == 200:
                    record("S5.proxy_recovers", "PASS",
                           "dashboard routes to new daemon after respawn (in-memory chat lost as expected)")
                else:
                    record("S5.proxy_recovers", "FAIL",
                           f"after daemon respawn, /api/cc/health = {code}")
            else:
                record("S5.daemon_respawn", "FAIL", "new daemon did not become ready 25s")

        # ── S6 · ai_ide_edits_ccdaemon_then_restart ────────────────────────
        # 用户最在意的核心场景: AI IDE 在 chat 框里改 ccdaemon 自身代码 (用 Edit 工具),
        # 然后用户跑 `omni cc daemon restart`. 浏览器 ws 应当干净断 + 看到清晰 exit 帧,
        # 不是无限重连或静默死.
        #
        # 协议: daemon restart 后, in-memory ChatSession 全失. 浏览器拿旧 sid 重连时
        # daemon ws_handler 看 _sessions.get(sid) is None → send error frame {kind:'error',
        # code:'not_found'} + ws.close(1000). 前端 wsAutoReconnect intentionalCloseCode=1000
        # 不再重连, UI 能合理处理.
        print("\n[S6/6] ai_ide_edits_ccdaemon_then_restart: 核心场景 — 用户 dogfood 主诉求")
        # 创新 chat session (S5 把 daemon kill 过, in-memory 失. 现在 daemon 在 S5 末复活了)
        code, body = http_post_json(f"{DASHBOARD}/api/cc/chat/sessions", {})
        if code != 200:
            record("S6.create_session", "FAIL", f"POST /api/cc/chat/sessions {code}")
        else:
            new_sid = json.loads(body)["id"]
            created_session_ids.append(new_sid)
            new_ws_url = f"ws://127.0.0.1:{DASHBOARD_PORT}/api/cc/chat/sessions/{new_sid}/ws"

            # 1. 真发 prompt 跑通一回合
            try:
                with ws_connect(new_ws_url, open_timeout=10) as ws_pre:
                    ws_pre.recv(timeout=5)  # snapshot
                    ws_pre.send(json.dumps({"type": "user.message",
                                            "content": "Reply with exactly: PRE-RESTART-OK"}))
                    text, ok = collect_assistant_text(ws_pre, deadline_s=PROMPT_TIMEOUT_S)
                    if not (ok and "PRE-RESTART-OK" in text):
                        record("S6.pre_restart_chat", "FAIL", f"ok={ok} text={text[:200]!r}")
                    else:
                        record("S6.pre_restart_chat", "PASS")
            except Exception as e:
                record("S6.pre_restart_chat", "FAIL", f"{type(e).__name__}: {e}")

            # 2. 模拟 AI IDE 改 ccdaemon/chat.py — touch 不改内容 (无副作用 marker)
            ccdaemon_chat = REPO_ROOT / "src" / "omnicompany" / "dashboard" / "ccdaemon" / "chat.py"
            try:
                from os import utime
                now = time.time()
                utime(ccdaemon_chat, (now, now))
                record("S6.ai_ide_touched_ccdaemon_file", "PASS",
                       f"touched {ccdaemon_chat.name} (mtime updated)")
            except OSError as e:
                record("S6.ai_ide_touched_ccdaemon_file", "FAIL", str(e))

            # 3. 用户跑 omni cc daemon restart (这是 plan §6 既定流程)
            try:
                rcode = subprocess.run(
                    [sys.executable, "-m", "omnicompany.cli.main", "cc", "daemon", "restart",
                     "--port", str(DAEMON_PORT)],
                    cwd=str(REPO_ROOT), capture_output=True, timeout=30,
                ).returncode
                if rcode == 0 and wait_until(lambda: http_get(f"{DAEMON}/health")[0] == 200, 15):
                    record("S6.daemon_restart_completed", "PASS")
                else:
                    record("S6.daemon_restart_completed", "FAIL", f"rcode={rcode}")
                # 重要: omni cc daemon restart 起的新 daemon 不是我们 spawn_daemon 的句柄,
                # 我们的 daemon_proc 已经死. cleanup 时要靠 lifecycle pid file 杀.
                daemon_proc = None
            except Exception as e:
                record("S6.daemon_restart_completed", "FAIL", f"{type(e).__name__}: {e}")

            # 4. 浏览器拿旧 sid 重连 — 应当收到 error 'not_found' + ws.close(1000)
            try:
                with ws_connect(new_ws_url, open_timeout=10) as ws_post:
                    # 等第一帧
                    end_t = time.time() + 5
                    got_error_frame = False
                    while time.time() < end_t:
                        try:
                            raw = ws_post.recv(timeout=2)
                        except TimeoutError:
                            continue
                        try:
                            frame = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        if frame.get("kind") == "error" and frame.get("code") == "not_found":
                            got_error_frame = True
                            break
                    if got_error_frame:
                        record("S6.post_restart_clean_exit", "PASS",
                               "old sid → daemon error frame 'not_found', ws close (no infinite reconnect)")
                    else:
                        record("S6.post_restart_clean_exit", "FAIL",
                               "expected error 'not_found' frame, did not arrive in 5s")
            except Exception as e:
                # 也可能是 ws 直接被 daemon refuse — 这也是清晰的"session 失" 信号
                msg = str(e)
                if "1000" in msg or "rejected" in msg.lower() or "404" in msg:
                    record("S6.post_restart_clean_exit", "PASS",
                           f"old sid → ws closed cleanly: {msg[:120]}")
                else:
                    record("S6.post_restart_clean_exit", "FAIL", f"{type(e).__name__}: {msg[:200]}")

            # 5. 用户开新 session — 验 chat 仍能正常工作
            code, body = http_post_json(f"{DASHBOARD}/api/cc/chat/sessions", {})
            if code != 200:
                record("S6.new_session_after_restart", "FAIL", f"create new sid {code}")
            else:
                fresh_sid = json.loads(body)["id"]
                created_session_ids.append(fresh_sid)
                fresh_url = f"ws://127.0.0.1:{DASHBOARD_PORT}/api/cc/chat/sessions/{fresh_sid}/ws"
                try:
                    with ws_connect(fresh_url, open_timeout=10) as ws_fresh:
                        ws_fresh.recv(timeout=5)  # snapshot
                        ws_fresh.send(json.dumps({"type": "user.message",
                                                  "content": "Reply with exactly: POST-RESTART-OK"}))
                        text, ok = collect_assistant_text(ws_fresh, deadline_s=PROMPT_TIMEOUT_S)
                        if ok and "POST-RESTART-OK" in text:
                            record("S6.new_session_after_restart", "PASS",
                                   "fresh chat session works post-restart")
                        else:
                            record("S6.new_session_after_restart", "FAIL",
                                   f"ok={ok} text={text[:200]!r}")
                except Exception as e:
                    record("S6.new_session_after_restart", "FAIL",
                           f"{type(e).__name__}: {str(e)[:200]}")

    finally:
        # cleanup: 删 chat sessions, kill 进程
        print("\n[cleanup] deleting test chat sessions, stopping processes...")
        for s in created_session_ids:
            try:
                http_delete(f"{DASHBOARD}/api/cc/chat/sessions/{s}", timeout=3)
            except Exception:
                pass
        kill_proc(dashboard_proc, force=True)
        kill_proc(daemon_proc, force=True)
        try:
            from omnicompany.dashboard.ccdaemon import lifecycle as _lc
            _lc.clear_pid()
        except Exception:
            pass

    # 汇总
    print("\n" + "═" * 60)
    print("dogfood 严密 e2e 测试汇总")
    print("═" * 60)
    pass_n = sum(1 for _, s, _ in results if s == "PASS")
    fail_n = sum(1 for _, s, _ in results if s == "FAIL")
    skip_n = sum(1 for _, s, _ in results if s == "SKIP")
    for n, s, note in results:
        print(f"  {s:4s}  {n}{(' — ' + note) if note else ''}")
    print(f"\n  PASS={pass_n}  FAIL={fail_n}  SKIP={skip_n}  total={len(results)}")
    return fail_n


if __name__ == "__main__":
    sys.exit(run())
