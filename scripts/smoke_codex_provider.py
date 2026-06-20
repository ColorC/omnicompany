# OMNI-PERSISTENT-SCRIPT owner=dashboard purpose=chat-interface-e2e-smoke
"""CodexProvider smoke test — 验 codex CLI 真接通跟事件流."""
import asyncio
from omnicompany.dashboard.ccdaemon.providers.codex import CodexProvider


async def main():
    provider = CodexProvider({
        "cwd": "/workspace/omnicompany",
        "codex_path": "C:/Users/user/AppData/Roaming/npm/codex.cmd",
    })

    print("[1] connect...")
    await provider.connect()
    print("    connected")

    print("[2] send_prompt('say hi briefly'). 收 NormalizedMessage 流, 上限 30 条...")
    messages_collected = []

    async def collector():
        async for nm in provider.consume_messages():
            messages_collected.append(nm)
            kind = nm.get("kind")
            if kind == "text":
                content = str(nm.get("content", ""))[:100]
                print(f"    [text]    {content!r}")
            elif kind == "thinking":
                content = str(nm.get("content", ""))[:100]
                print(f"    [think]   {content!r}")
            elif kind == "tool_use":
                print(f"    [tool>]   {nm.get('toolName')} input={str(nm.get('input'))[:80]}")
            elif kind == "tool_result":
                result = str(nm.get('result', ''))[:80]
                print(f"    [tool<]   err={nm.get('isError')} exit={nm.get('exitCode')} result={result!r}")
            elif kind == "session_created":
                print(f"    [session] {nm.get('newSessionId')}")
            elif kind == "complete":
                print(f"    [done]    exit={nm.get('exitCode')} aborted={nm.get('aborted')}")
                return
            elif kind == "error":
                print(f"    [ERROR]   {nm.get('error')}")
                return
            elif kind == "status":
                print(f"    [status]  {nm.get('text')}")
            else:
                print(f"    [{kind}]")
            if len(messages_collected) >= 30:
                return

    await provider.send_prompt("Say hi briefly. No code.")
    try:
        await asyncio.wait_for(collector(), timeout=120)
    except asyncio.TimeoutError:
        print("    TIMEOUT")

    print(f"\n[3] 总收 {len(messages_collected)} 条 NormalizedMessage")
    kinds = [m.get("kind") for m in messages_collected]
    print(f"    kind 序列: {kinds}")

    print("[4] disconnect...")
    await provider.disconnect()
    print("    disconnected")


if __name__ == "__main__":
    asyncio.run(main())
