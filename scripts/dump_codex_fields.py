# OMNI-PERSISTENT-SCRIPT owner=dashboard purpose=chat-interface-e2e-smoke
"""跑 codex 一个 turn dump 所有字段, 看 codex 有没有官方 context% 字段."""
import asyncio, json, websockets, httpx

URL = "http://127.0.0.1:8210"


async def main():
    async with httpx.AsyncClient() as cx:
        r = await cx.post(f"{URL}/api/cc/chat/sessions", json={"provider": "codex"})
        sid = r.json()["id"]
        print(f"session: {sid}")
    ws_url = f"ws://127.0.0.1:8210/api/cc/chat/sessions/{sid}/ws"
    async with websockets.connect(ws_url) as ws:
        await ws.send(json.dumps({"type": "user.message", "content": "hi"}))
        seen_kinds = {}
        try:
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=15)
                f = json.loads(raw)
                k = f.get("kind")
                seen_kinds.setdefault(k, []).append(f)
                if k == "result":
                    break
        except asyncio.TimeoutError:
            print("(timeout)")

    for k, frames in seen_kinds.items():
        print(f"\n--- kind={k} (count={len(frames)}) ---")
        print(json.dumps(frames[0], indent=2, ensure_ascii=False, default=str)[:1500])

asyncio.run(main())
