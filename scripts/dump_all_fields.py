# OMNI-PERSISTENT-SCRIPT owner=dashboard purpose=chat-interface-e2e-smoke
"""跑一个 turn, 把 claude-agent-sdk 收到的所有 message 类型的完整 raw 字段全 dump.
看官方有没有暴露"context window used / left" 类字段我们漏抄了."""
import asyncio, json, websockets, httpx

URL = "http://127.0.0.1:8210"


async def main():
    async with httpx.AsyncClient() as cx:
        r = await cx.post(f"{URL}/api/cc/chat/sessions", json={"provider": "claude_code"})
        sid = r.json()["id"]
        print(f"session: {sid}")
    ws_url = f"ws://127.0.0.1:8210/api/cc/chat/sessions/{sid}/ws"
    async with websockets.connect(ws_url) as ws:
        await ws.send(json.dumps({"type": "user.message", "content": "hi"}))
        seen_kinds = {}
        try:
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=10)
                f = json.loads(raw)
                k = f.get("kind")
                seen_kinds.setdefault(k, []).append(f)
                if k == "result":
                    break
        except asyncio.TimeoutError:
            pass

    print("\n========= ALL KINDS SEEN =========")
    for k, frames in seen_kinds.items():
        print(f"\n--- kind={k} (count={len(frames)}) ---")
        print(f"FIRST: {json.dumps(frames[0], indent=2, ensure_ascii=False, default=str)[:2000]}")

asyncio.run(main())
