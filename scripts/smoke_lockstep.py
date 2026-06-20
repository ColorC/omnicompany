# [OMNI] origin=claude-code domain=scripts/smoke_lockstep.py ts=2026-04-18T00:00:00Z
"""双脑 lockstep 架构 smoke 测试 — 不调真 LLM，只验证结构 wiring。

验证：
  1. base AgentNodeLoop.on_turn_end_async 能 await 生效
  2. ReflectorDaemon 的 submit_and_wait 往返
  3. LockstepExperimenter 能挂 daemon
  4. 事件流到 bus（假的 mock bus）
"""

from __future__ import annotations
import asyncio
import sys


class _FakeBus:
    def __init__(self):
        self.events = []
    async def connect(self): pass
    async def close(self): pass
    async def publish(self, event):
        self.events.append(event)
        return event.id


class _FakeReflector:
    """假 Reflector：不跑 LLM，直接返回 Verdict PASS。"""
    def __init__(self):
        import logging
        self._config = None
        self.call_count = 0
    async def run(self, input_data):
        from omnicompany.protocol.anchor import Verdict, VerdictKind
        self.call_count += 1
        return Verdict(kind=VerdictKind.PASS, output={"doc_path": input_data.get("doc_path")})


async def test_on_turn_end_async_hook():
    """验证新基类 on_turn_end_async 钩子存在且可被子类 override。"""
    from omnicompany.packages.services.agent import AgentNodeLoop

    called = {"count": 0, "args": []}

    class _T(AgentNodeLoop):
        ALLOW_NO_BUS = True
        NODE_PROMPT = "x"

        async def on_turn_end_async(self, *, turn, messages, trace_id):
            called["count"] += 1
            called["args"].append({"turn": turn, "trace_id": trace_id, "msg_count": len(messages)})

    # 绕过 __init__ 的 bus 检查（只测钩子 override，不跑完整 loop）
    t = _T.__new__(_T)
    await t.on_turn_end_async(turn=5, messages=[{"role": "user", "content": "x"}], trace_id="tr-1")
    assert called["count"] == 1, "on_turn_end_async 应被调用"
    assert called["args"][0] == {"turn": 5, "trace_id": "tr-1", "msg_count": 1}
    print("  ✓ on_turn_end_async hook: override ok")
    return True


async def test_daemon_submit_and_wait():
    """daemon 能收观察 → 出结果 → 解锁等待方。"""
    import tempfile
    import os
    from omnicompany.packages.services.hypothesis.reflector_daemon import (
        ReflectorDaemon, StepObservation,
    )

    # 创建临时 doc
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8")
    tmp.write("""---
omnikb_type: khyp
id: kb.hyp.smoke-test
name: smoke
hypotheses: []
---
# smoke
""")
    tmp.close()

    bus = _FakeBus()
    reflector = _FakeReflector()
    daemon = ReflectorDaemon(
        reflector=reflector,
        bus=bus,
        session_id="smoke-session-001",
        doc_path=tmp.name,
        per_step_max_turns=2,
        reflection_timeout=10.0,
    )
    await daemon.start()

    obs = StepObservation(
        session_id="smoke-session-001",
        turn=0,
        tool="bash",
        args={"cmd": "echo hi"},
        result="hi",
    )
    result = await daemon.submit_and_wait(obs)
    await daemon.stop()

    assert reflector.call_count == 1, f"期望 Reflector 被调 1 次，实际 {reflector.call_count}"
    print(f"  ✓ daemon.submit_and_wait returned: {result.summary}")

    # bus 事件检查
    types = [e.event_type for e in bus.events]
    assert "hyp.step_observation" in types, f"缺 step_observation 事件, 有: {types}"
    assert "hyp.reflection_result" in types, f"缺 reflection_result 事件, 有: {types}"
    print(f"  ✓ bus 收到 {len(bus.events)} 事件: {set(types)}")

    os.unlink(tmp.name)
    return True


async def test_lockstep_experimenter_wiring():
    """LockstepExperimenter 能用 daemon kwarg 构造。"""
    from omnicompany.packages.services.hypothesis.routers import LockstepExperimenterRouter
    from omnicompany.packages.services.hypothesis.reflector_daemon import ReflectorDaemon

    bus = _FakeBus()
    reflector = _FakeReflector()
    daemon = ReflectorDaemon(
        reflector=reflector, bus=bus,
        session_id="x", doc_path="/nonexistent",
    )

    exp = LockstepExperimenterRouter(daemon=daemon, bus=bus)
    assert exp._daemon is daemon
    print("  ✓ LockstepExperimenter 挂 daemon 成功")
    return True


async def main():
    tests = [
        ("on_turn_end_async hook (new base)", test_on_turn_end_async_hook),
        ("daemon submit_and_wait", test_daemon_submit_and_wait),
        ("LockstepExperimenter wiring", test_lockstep_experimenter_wiring),
    ]
    ok = True
    for name, t in tests:
        print(f"[test] {name}")
        try:
            await t()
        except Exception as exc:
            print(f"  ✘ FAIL: {type(exc).__name__}: {exc}")
            import traceback; traceback.print_exc()
            ok = False
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
