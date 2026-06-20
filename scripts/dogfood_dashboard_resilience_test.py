#!/usr/bin/env python3
# [OMNI] origin=ai-ide ts=2026-05-09 type=test
# [OMNI] material_id="material:scripts.dogfood_dashboard_resilience.scenarios.py"
"""dogfood 韧性测试 — 起 daemon + dashboard 双进程, 跑 5 个场景验证道路.

跑法:
    python scripts/dogfood_dashboard_resilience_test.py

不依赖真 claude binary (避免 chat 路线必须装/登录 claude). 全部用 health
端点跟 echo WebSocket 验证进程隔离 + 反向代理 + 重连协议是否真扛得住.

场景
----
1. setup            起 daemon → 验 daemon /health 直连 OK; 起 dashboard → 验
                    /api/cc/health 经反向代理转到 daemon /cc/health
2. dashboard_reload 改 controlplane 任意文件触发 dashboard reload, 验
                    daemon pid 不变, daemon /health 仍 OK
3. daemon_restart   omni cc daemon restart 触发 daemon 换 pid, 验 dashboard
                    没死 (pid 不变), /api/cc/health 重新可达
4. ws_echo          浏览器 → dashboard /api/cc/echo → daemon /cc/echo, 双向
                    JSON 帧通; 100 来回 RTT p50/p99 基线
5. ws_through_reload WS echo 跑中触发 dashboard reload, 验 WS 自动重连后
                    新连接仍跟 daemon 双向通 (浏览器 wsAutoReconnect 协议)

每场景 PASS/FAIL/SKIP, 末尾汇总. 退出码 = 失败场景数.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

# websockets 为同步 helper 包 (我们用 sync API 简化测试代码)
try:
    from websockets.sync.client import connect as ws_connect
except ImportError as e:
    print(f"FATAL: websockets >= 12 needed (got import error: {e})", file=sys.stderr)
    sys.exit(2)


REPO_ROOT = Path(__file__).resolve().parent.parent
DAEMON_PORT = int(os.environ.get("OMNI_DOGFOOD_DAEMON_PORT", "8221"))
DASHBOARD_PORT = int(os.environ.get("OMNI_DOGFOOD_DASHBOARD_PORT", "8220"))
DASHBOARD = f"http://127.0.0.1:{DASHBOARD_PORT}"
DAEMON = f"http://127.0.0.1:{DAEMON_PORT}"

# 场景结果聚合
results: list[tuple[str, str, str]] = []  # (name, status, note)


def http_get(url: str, timeout: float = 3.0) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
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


# ─────────────────────────────────────────────────────────────────
# 场景实施
# ─────────────────────────────────────────────────────────────────


def run() -> int:
    # ── 0. 准备: 杀任何占用端口的旧进程, 清陈旧 pid 文件
    print(f"[setup] using daemon port={DAEMON_PORT} dashboard port={DASHBOARD_PORT}")
    subprocess.run([sys.executable, "-m", "omnicompany.cli.main", "cc", "daemon", "stop"],
                   cwd=str(REPO_ROOT), capture_output=True)

    daemon_proc: subprocess.Popen | None = None
    dashboard_proc: subprocess.Popen | None = None

    try:
        # ── 1. setup: 起 daemon + dashboard
        print("\n[1/5] setup: spawn daemon then dashboard, verify reverse proxy")
        env = os.environ.copy()
        env["OMNI_CC_DAEMON_PORT"] = str(DAEMON_PORT)
        creationflags = 0x00000200 if sys.platform == "win32" else 0  # CREATE_NEW_PROCESS_GROUP

        daemon_proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn",
             "omnicompany.dashboard.ccdaemon.main:app",
             "--host", "127.0.0.1", "--port", str(DAEMON_PORT),
             "--log-level", "warning"],
            cwd=str(REPO_ROOT), env=env, creationflags=creationflags,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if not wait_until(lambda: http_get(f"{DAEMON}/health")[0] == 200, 20):
            record("setup.daemon_ready", "FAIL", "daemon /health did not respond in 20s")
            return 1
        record("setup.daemon_ready", "PASS")

        dash_log = REPO_ROOT / "data" / "dogfood_dashboard.log"
        dash_log.parent.mkdir(parents=True, exist_ok=True)
        dash_log_fd = open(dash_log, "wb")
        dashboard_proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn",
             "omnicompany.dashboard.app:app",
             "--host", "127.0.0.1", "--port", str(DASHBOARD_PORT),
             "--reload",
             "--reload-dir", str(REPO_ROOT / "src" / "omnicompany" / "dashboard"),
             # 直接传 ccdaemon 目录路径 (不带 wildcard), uvicorn resolve_reload_patterns
             # 把它识别为 directory 加入 reload_dirs_excludes. wildcard 会被某些 shell
             # 在 cmdline 阶段展开 (即使 list 形式 Popen 在 Windows + git-bash 环境下也踩过).
             "--reload-exclude", "src/omnicompany/dashboard/ccdaemon",
             "--log-level", "info"],
            cwd=str(REPO_ROOT),
            stdout=dash_log_fd, stderr=subprocess.STDOUT,
        )
        if not wait_until(lambda: http_get(f"{DASHBOARD}/api/cc/health")[0] == 200, 45):
            record("setup.dashboard_proxy", "FAIL", "/api/cc/health did not 200 in 45s (uvicorn --reload startup is slow)")
            return 1
        record("setup.dashboard_proxy", "PASS")

        # ── 2. dashboard reload: 改非 ccdaemon 文件触发 reload, 验 daemon 不动
        print("\n[2/5] dashboard_reload: touch controlplane file, verify daemon untouched")
        from omnicompany.dashboard.ccdaemon import lifecycle
        before = lifecycle.read_status()
        if not (before.alive and before.pid):
            record("dashboard_reload", "SKIP", "daemon pid file unreadable")
        else:
            target = REPO_ROOT / "src" / "omnicompany" / "dashboard" / "controlplane" / "notes.py"
            if not target.is_file():
                record("dashboard_reload", "SKIP", f"target not found: {target}")
            else:
                target.touch()
                # uvicorn reload 默认监听 ~250ms 周期, 需要时间触发 + 重载完成
                time.sleep(4)
                # 验 dashboard 还能响应
                code, _ = http_get(f"{DASHBOARD}/api/cc/health", timeout=5)
                after = lifecycle.read_status()
                if after.pid == before.pid and after.alive:
                    if code == 200:
                        record("dashboard_reload", "PASS",
                               f"daemon pid stayed {before.pid} after dashboard reload")
                    else:
                        record("dashboard_reload", "FAIL",
                               f"daemon pid OK ({before.pid}) but dashboard /api/cc/health {code}")
                else:
                    record("dashboard_reload", "FAIL",
                           f"daemon pid changed: {before.pid} → {after.pid}")

        # ── 3. daemon restart: 显式 restart 后 dashboard 仍活
        print("\n[3/5] daemon_restart: explicit daemon restart, dashboard stays up")
        # 跑 omni cc daemon restart, 它会 stop 然后 spawn 新 daemon
        # 注意: 这里必须直接 kill + respawn daemon, 因为 daemon_proc 是我们这里 Popen 的,
        #      omni cc daemon stop 会 TerminateProcess 它 (好), 但 omni cc daemon start
        #      会 spawn 个新 daemon (没有 daemon_proc 句柄, 不影响我们 cleanup), 跳过 start
        try:
            old_pid = lifecycle.read_status().pid
            subprocess.run(
                [sys.executable, "-m", "omnicompany.cli.main", "cc", "daemon", "stop"],
                cwd=str(REPO_ROOT), capture_output=True, timeout=10,
            )
            time.sleep(2)
            # 重新起一个 daemon (用我们这里的 Popen, 这样 cleanup 时能 kill)
            daemon_proc = subprocess.Popen(
                [sys.executable, "-m", "uvicorn",
                 "omnicompany.dashboard.ccdaemon.main:app",
                 "--host", "127.0.0.1", "--port", str(DAEMON_PORT),
                 "--log-level", "warning"],
                cwd=str(REPO_ROOT), env=env, creationflags=creationflags,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            if not wait_until(lambda: http_get(f"{DAEMON}/health")[0] == 200, 15):
                record("daemon_restart", "FAIL", "daemon did not come back in 15s")
            else:
                new_pid = lifecycle.read_status().pid
                code_dash, _ = http_get(f"{DASHBOARD}/api/cc/health", timeout=5)
                if new_pid != old_pid and code_dash == 200:
                    record("daemon_restart", "PASS",
                           f"daemon pid {old_pid} → {new_pid}, dashboard still routes")
                else:
                    record("daemon_restart", "FAIL",
                           f"old={old_pid} new={new_pid} dashboard_code={code_dash}")
        except Exception as e:
            record("daemon_restart", "FAIL", f"{type(e).__name__}: {e}")

        # ── 4. ws_echo: 浏览器 → dashboard → daemon WS 桥接 (含 RTT 基线)
        print("\n[4/5] ws_echo: WebSocket bridged through dashboard, RTT baseline")
        try:
            samples_ms: list[float] = []
            with ws_connect(f"ws://127.0.0.1:{DASHBOARD_PORT}/api/cc/echo", open_timeout=5) as ws:
                for i in range(50):
                    t0 = time.time()
                    ws.send(f"ping-{i}")
                    msg = ws.recv(timeout=3)
                    samples_ms.append((time.time() - t0) * 1000)
                    if msg != f"echo:ping-{i}":
                        record("ws_echo", "FAIL",
                               f"frame {i}: expected 'echo:ping-{i}' got {msg!r}")
                        break
                else:
                    samples_ms.sort()
                    p50 = samples_ms[len(samples_ms) // 2]
                    p99 = samples_ms[max(0, int(len(samples_ms) * 0.99) - 1)]
                    record("ws_echo", "PASS",
                           f"50 frames, p50={p50:.1f}ms p99={p99:.1f}ms")
        except Exception as e:
            record("ws_echo", "FAIL", f"{type(e).__name__}: {e}")

        # ── 5. ws_through_reload: 跑 WS 中触发 dashboard reload, 验自动重连
        print("\n[5/5] ws_through_reload: dashboard reload mid-WS, browser must reconnect")
        # 这是浏览器侧的事 (wsAutoReconnect.ts 在前端). 后端测试只能验"WS 断了 + 重连后
        # 仍能联通 daemon" 的服务端契约. 真正端到端验需要 Playwright (留独立 e2e).
        try:
            target = REPO_ROOT / "src" / "omnicompany" / "dashboard" / "controlplane" / "notes.py"
            with ws_connect(f"ws://127.0.0.1:{DASHBOARD_PORT}/api/cc/echo", open_timeout=5) as ws1:
                ws1.send("before-reload")
                msg = ws1.recv(timeout=3)
                assert msg == "echo:before-reload", f"got {msg!r}"
                # 触发 dashboard reload
                target.touch()
                time.sleep(5)
                # ws1 应当被 dashboard 重启时关掉 (后端 task cancelled). 浏览器侧
                # wsAutoReconnect 会立即重连. 这里我们模拟新连一次.
            with ws_connect(f"ws://127.0.0.1:{DASHBOARD_PORT}/api/cc/echo", open_timeout=10) as ws2:
                ws2.send("after-reload")
                msg = ws2.recv(timeout=3)
                if msg == "echo:after-reload":
                    record("ws_through_reload", "PASS",
                           "新 WS 连上 dashboard 仍能转发到 daemon (前端 wsAutoReconnect 协议在浏览器侧自动)")
                else:
                    record("ws_through_reload", "FAIL", f"got {msg!r}")
        except Exception as e:
            record("ws_through_reload", "FAIL", f"{type(e).__name__}: {e}")

    finally:
        # cleanup
        print("\n[cleanup] stopping dashboard + daemon...")
        for p in [dashboard_proc, daemon_proc]:
            if p is None:
                continue
            try:
                if sys.platform == "win32":
                    p.kill()
                else:
                    p.send_signal(signal.SIGTERM)
                    try:
                        p.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        p.kill()
            except Exception:
                pass
        # 也清 pid 文件 (防止 daemon CLI 误判 alive)
        try:
            from omnicompany.dashboard.ccdaemon import lifecycle as _lc
            _lc.clear_pid()
        except Exception:
            pass

    # 汇总
    print("\n" + "═" * 60)
    print("dogfood 韧性测试汇总")
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
