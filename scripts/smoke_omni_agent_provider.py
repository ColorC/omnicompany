# OMNI-PERSISTENT-SCRIPT owner=dashboard purpose=chat-interface-e2e-smoke
"""OmniAgentProvider smoke test — 起最简 AgentNodeLoop 子类, 验 NormalizedMessage 流."""
import asyncio
from omnicompany.dashboard.ccdaemon.providers.omni_agent import OmniAgentProvider
from omnicompany.packages.services._core.agent.loop import AgentNodeLoop
from omnicompany.packages.services._core.agent.routers.single_tool import FinishRouter
from omnicompany.bus.memory import MemoryBus


# 最简 chat agent — system prompt 引导直接调 finish, 不真去调外部工具
class SmokeChatAgent(AgentNodeLoop):
    NODE_PROMPT = (
        "你是测试助手. 用户给你一句话, 你必须**立即**调 finish 工具返回简短回复.\n"
        "不要调任何其他工具. 不要解释. 立即 finish."
    )
    TOOL_ROUTERS = [FinishRouter]


async def main():
    bus = MemoryBus()
    await bus.connect()

    provider = OmniAgentProvider({
        "agent_class": SmokeChatAgent,
        "agent_bus": bus,
        "model": None,  # 走默认 qwen-3.6-plus
    })

    print("[1] connect...")
    await provider.connect()
    print("    connected")

    print("[2] send_prompt('say hi'). 收 NormalizedMessage 流, 上限 30 条...")
    messages_collected = []

    async def collector():
        async for nm in provider.consume_messages():
            messages_collected.append(nm)
            kind = nm.get("kind")
            if kind == "text":
                content = str(nm.get("content", ""))[:80]
                print(f"    [text]    {content!r}")
            elif kind == "thinking":
                content = str(nm.get("content", ""))[:80]
                print(f"    [think]   {content!r}")
            elif kind == "tool_use":
                print(f"    [tool>]   {nm.get('toolName')} input={str(nm.get('input'))[:60]}")
            elif kind == "tool_result":
                result = str(nm.get('result', ''))[:60]
                print(f"    [tool<]   err={nm.get('isError')} result={result!r}")
            elif kind == "session_created":
                print(f"    [session] {nm.get('newSessionId')}")
            elif kind == "complete":
                print(f"    [done]    exit={nm.get('exitCode')} aborted={nm.get('aborted')}")
                return
            elif kind == "error":
                print(f"    [ERROR]   {nm.get('error')}")
                return
            else:
                print(f"    [{kind}]")
            if len(messages_collected) >= 30:
                return

    await provider.send_prompt("say hi")
    await asyncio.wait_for(collector(), timeout=120)

    print(f"\n[3] 总收 {len(messages_collected)} 条 NormalizedMessage")
    kinds = [m.get("kind") for m in messages_collected]
    print(f"    kind 序列: {kinds}")

    assert any(k == "session_created" for k in kinds), "FAIL: 缺 session_created"
    assert any(k == "complete" for k in kinds), "FAIL: 缺 complete"
    # text 或 tool_use 至少一个 (agent 应该至少调了 finish, 或者出了 text)
    assert any(k in ("text", "tool_use") for k in kinds), "FAIL: 缺 text/tool_use"
    print("\n[4] 必要 kind 全到 (session_created / [text|tool_use] / complete) - PASS")

    print("[5] disconnect...")
    await provider.disconnect()
    await bus.close()
    print("    disconnected")


if __name__ == "__main__":
    asyncio.run(main())
