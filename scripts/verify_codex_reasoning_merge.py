# OMNI-PERSISTENT-SCRIPT owner=dashboard purpose=chat-interface-e2e-smoke
"""验 codex 多步 reasoning 真合并成一条 thinking NormalizedMessage."""
import asyncio
from omnicompany.dashboard.ccdaemon.providers.codex import CodexProvider


async def main():
    provider = CodexProvider({
        "cwd": "/workspace/omnicompany",
        "codex_path": "C:/Users/user/AppData/Roaming/npm/codex.cmd",
    })

    await provider.connect()

    # 复杂提问让 codex 思考多步
    messages = []
    async def collector():
        async for nm in provider.consume_messages():
            messages.append(nm)
            kind = nm.get("kind")
            if kind == "thinking":
                content = str(nm.get("content", ""))
                print(f"[thinking] {len(content)} 字符: {content[:120]!r}")
            elif kind == "text":
                content = str(nm.get("content", ""))[:80]
                print(f"[text] {content!r}")
            elif kind == "complete":
                print(f"[done] exit={nm.get('exitCode')}")
                return
            elif kind == "error":
                print(f"[error] {nm.get('error')}")
                return

    # 一个需要思考的提问
    await provider.send_prompt("用 100 字解释什么是 git rebase, 不要调用任何工具.")
    try:
        await asyncio.wait_for(collector(), timeout=120)
    except asyncio.TimeoutError:
        print("TIMEOUT")

    kinds = [m.get("kind") for m in messages]
    thinking_count = sum(1 for k in kinds if k == "thinking")
    print(f"\nkind 序列: {kinds}")
    print(f"thinking NormalizedMessage 数: {thinking_count} (期望 1 整段, 不是 N 个零碎)")
    if thinking_count <= 1:
        print("=== PASS · reasoning 合并成功 ===")
    else:
        print(f"=== FAIL · 还是 {thinking_count} 条 thinking ===")

    await provider.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
