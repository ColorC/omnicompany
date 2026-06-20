# OMNI-PERSISTENT-SCRIPT owner=dashboard purpose=chat-interface-e2e-smoke
"""跑一个 turn 抓 result frame 的 usage 完整结构, 看 Python SDK 里到底是什么形态."""
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
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=60)
            f = json.loads(raw)
            if f.get("kind") == "result":
                print("--- RESULT FRAME ---")
                print(json.dumps(f, indent=2, ensure_ascii=False))
                break

asyncio.run(main())
