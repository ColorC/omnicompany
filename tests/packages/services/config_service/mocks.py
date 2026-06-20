# [OMNI] origin=claude-code domain=tests/config_service ts=2026-04-24T00:00:00Z type=test_infra
"""MockFeishuNotifier · 截断协作平台真调用 · 记录调用历史供断言.

**动机** (L1 2026-04-24): "协作平台交互都可以集中测试, 非和我互动测试.
需要 mock 中断处位于收发位置截断. 测试时不应真发消息, 除非要测格式和接口."

**策略**:
- Mock 位置: FeishuNotifier 公共接口 (duck-type · 和真 notifier 签名 1:1)
- 不走 WebBus / HTTP · 直接记录到内存 list + 伪造合法响应 dict
- PATCH API 走 notifier._web_bus.request("PATCH", ...) · 也 mock 掉 (MockWebBus)
- message_id / thread_id 伪造 · 格式对齐协作平台真实 (om_xxx / omt_xxx)

**调用记录 schema** (self.calls: list[dict]):
  {
    "method": "send_card" | "send_text" | "send_in_thread" | "reply_message"
              | "add_reaction" | "patch_message",
    "kwargs": {...},        # 原样记录调用参数 (供断言)
    "returned_msg_id": str,  # 伪造 om_xxx
    "returned_thread_id": str,  # omt_xxx (仅 reply_in_thread=True 时非空)
  }
"""
from __future__ import annotations

import itertools
import json
from typing import Any


class _MockWebResponse:
    """模拟 WebBus.WebResponse · 用于 PATCH 返回."""
    def __init__(self, status_code: int = 200, body: dict | None = None):
        self.status_code = status_code
        body = body if body is not None else {"code": 0, "msg": "success"}
        self.body = json.dumps(body).encode("utf-8")

    def json(self) -> dict:
        return json.loads(self.body.decode("utf-8"))

    @property
    def text(self) -> str:
        return self.body.decode("utf-8")


class MockWebBus:
    """模拟 WebBus · 只拦 request(PATCH) 用于 StreamingCardController PATCH 卡.

    其他方法 (get/post 等) 不被 notifier mock 用到, 留空 fallback.
    """
    def __init__(self, notifier: "MockFeishuNotifier"):
        self._notifier = notifier

    def request(self, method: str, url: str, **kw) -> _MockWebResponse:
        # 只拦 PATCH /im/v1/messages/:id (streaming_card._patch_message_card)
        if method.upper() == "PATCH" and "/im/v1/messages/" in url:
            msg_id = url.rsplit("/", 1)[-1].split("?")[0]
            card_content = None
            try:
                body = kw.get("json") or {}
                raw = body.get("content", "")
                card_content = json.loads(raw) if isinstance(raw, str) else raw
            except Exception:
                card_content = {"_parse_error": str(kw.get("json"))}
            self._notifier.calls.append({
                "method": "patch_message",
                "message_id": msg_id,
                "card": card_content,
            })
            return _MockWebResponse(200, {"code": 0, "msg": "success"})
        # 其他未知 PATCH · 返 ok 不崩
        return _MockWebResponse(200, {"code": 0, "msg": "success (mock)"})

    def post(self, *a, **kw): return _MockWebResponse()
    def get(self, *a, **kw): return _MockWebResponse()
    def patch(self, *a, **kw): return self.request("PATCH", *a, **kw)
    def delete(self, *a, **kw): return _MockWebResponse()


class MockFeishuNotifier:
    """和 FeishuNotifier 公共接口 duck-type 兼容 · 所有调用记录到 self.calls."""

    def __init__(self):
        self.calls: list[dict] = []
        self._msg_counter = itertools.count(1)
        self._thread_counter = itertools.count(1)
        # 供 streaming_card 用 (它直接访问 notifier._web_bus / _ensure_token / _api_base)
        self._web_bus = MockWebBus(self)
        self._api_base = "https://mock.feishu/open-apis"

    # ──────────── duck-type 出来的接口 ────────────

    def _ensure_token(self) -> str:
        return "mock-token"

    def _fake_msg_id(self) -> str:
        n = next(self._msg_counter)
        return f"om_mock{n:016x}"

    def _fake_thread_id(self) -> str:
        n = next(self._thread_counter)
        return f"omt_mock{n:010x}"

    # ──────────── 公共 API ────────────

    def send_text(self, open_id: str, text: str) -> dict:
        msg_id = self._fake_msg_id()
        self.calls.append({
            "method": "send_text",
            "open_id": open_id,
            "text": text,
            "returned_msg_id": msg_id,
        })
        return {"code": 0, "data": {"message_id": msg_id}}

    def send_card(self, open_id: str, card: dict) -> dict:
        msg_id = self._fake_msg_id()
        self.calls.append({
            "method": "send_card",
            "open_id": open_id,
            "card": card,
            "returned_msg_id": msg_id,
        })
        return {"code": 0, "data": {"message_id": msg_id}}

    def send_in_thread(self, anchor_message_id: str, content: Any, *, msg_type: str = "text") -> dict:
        msg_id = self._fake_msg_id()
        thread_id = self._fake_thread_id()
        self.calls.append({
            "method": "send_in_thread",
            "anchor_message_id": anchor_message_id,
            "content": content,
            "msg_type": msg_type,
            "returned_msg_id": msg_id,
            "returned_thread_id": thread_id,
        })
        return {"code": 0, "data": {"message_id": msg_id, "thread_id": thread_id}}

    def reply_message(
        self, message_id: str, content: Any,
        *, msg_type: str = "text", reply_in_thread: bool = False,
    ) -> dict:
        msg_id = self._fake_msg_id()
        thread_id = self._fake_thread_id() if reply_in_thread else ""
        self.calls.append({
            "method": "reply_message",
            "reply_to": message_id,
            "content": content,
            "msg_type": msg_type,
            "reply_in_thread": reply_in_thread,
            "returned_msg_id": msg_id,
            "returned_thread_id": thread_id,
        })
        return {"code": 0, "data": {"message_id": msg_id, "thread_id": thread_id}}

    def add_reaction(self, message_id: str, emoji_type: str = "OK") -> dict:
        self.calls.append({
            "method": "add_reaction",
            "message_id": message_id,
            "emoji_type": emoji_type,
        })
        return {"code": 0, "data": {"reaction_id": f"rxn-{message_id[-8:]}"}}

    # ──────────── 辅助 (供断言) ────────────

    def methods(self) -> list[str]:
        return [c["method"] for c in self.calls]

    def find(self, method: str) -> list[dict]:
        return [c for c in self.calls if c["method"] == method]

    def first(self, method: str) -> dict | None:
        xs = self.find(method)
        return xs[0] if xs else None

    def clear(self) -> None:
        self.calls.clear()
