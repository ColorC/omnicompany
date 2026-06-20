# OMNI-PERSISTENT-SCRIPT owner=dashboard purpose=chat-interface-e2e-smoke
"""ClaudeCodeProvider smoke test — 创 provider, send 'hi', 验 NormalizedMessage 流真出来."""
import asyncio
from omnicompany.dashboard.ccdaemon.providers.claude_code import ClaudeCodeProvider


async def main():
    provider = ClaudeCodeProvider({
        "cwd": "/workspace/omnicompany",
        "permission_mode": "bypassPermissions",
    })

    print("[1] connect...")
    await provider.connect()
    print("    connected")

    print("[2] send_prompt('hi'). 收 NormalizedMessage 流, 上限 30 条...")
    messages_collected = []
    async def collector():
        async for nm in provider.consume_messages():
            messages_collected.append(nm)
            kind = nm.get("kind")
            if kind == "text":
                content = nm.get("content", "")[:60]
                print(f"    [text]    {content!r}")
            elif kind == "thinking":
                content = nm.get("content", "")[:60]
                print(f"    [think]   {content!r}")
            elif kind == "tool_use":
                print(f"    [tool>]   {nm.get('toolName')} input={str(nm.get('input'))[:50]}")
            elif kind == "tool_result":
                print(f"    [tool<]   id={nm.get('toolId')} err={nm.get('isError')}")
            elif kind == "session_created":
                print(f"    [session] {nm.get('newSessionId')}")
            elif kind == "complete":
                print(f"    [done]    exit={nm.get('exitCode')} actual_sid={nm.get('actualSessionId')}")
                return  # 完结一个 turn 就退
            elif kind == "error":
                print(f"    [ERROR]   {nm.get('error')}")
                return
            else:
                print(f"    [{kind}]")
            if len(messages_collected) >= 30:
                return

    await provider.send_prompt("hi")
    await asyncio.wait_for(collector(), timeout=60)

    print(f"\n[3] 总收 {len(messages_collected)} 条 NormalizedMessage")
    kinds = [m.get("kind") for m in messages_collected]
    print(f"    kind 序列: {kinds}")

    assert any(k == "session_created" for k in kinds), "FAIL: 缺 session_created"
    assert any(k == "text" or k == "thinking" for k in kinds), "FAIL: 缺 assistant 文本/thinking"
    assert any(k == "complete" for k in kinds), "FAIL: 缺 complete"
    print("\n[4] 三个必要 kind 全到 (session_created / text|thinking / complete) - PASS")

    print("[5] disconnect...")
    await provider.disconnect()
    print("    disconnected")


if __name__ == "__main__":
    asyncio.run(main())
