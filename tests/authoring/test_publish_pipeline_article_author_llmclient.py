from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from omnicompany.packages.services._authoring.publish_pipeline.workers import article_author


class _FakeTextBlock(SimpleNamespace):
    type = "text"


class _FakeToolUse(SimpleNamespace):
    type = "tool_use"


def test_article_author_agent_loop_uses_llmclient_and_preserves_reasoning(monkeypatch) -> None:
    monkeypatch.setattr(article_author, "_ensure_the_company_api_key", lambda: None)

    class FakeLLMClient:
        instances: list["FakeLLMClient"] = []

        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs
            self.calls: list[dict[str, Any]] = []
            FakeLLMClient.instances.append(self)

        def call(self, **kwargs: Any) -> Any:
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                return SimpleNamespace(
                    content=[
                        _FakeTextBlock(text="plan"),
                        _FakeToolUse(
                            id="tc_append_1",
                            name="append_article",
                            input={"content": "# Title\nBody"},
                        ),
                    ],
                    stop_reason="tool_calls",
                    reasoning_content="reasoning trace",
                )

            messages = kwargs["messages"]
            assistant_msg = messages[-2]
            tool_result_msg = messages[-1]
            assert assistant_msg["reasoning_content"] == "reasoning trace"
            assert assistant_msg["content"][1] == {
                "type": "tool_use",
                "id": "tc_append_1",
                "name": "append_article",
                "input": {"content": "# Title\nBody"},
            }
            assert tool_result_msg["content"][0]["type"] == "tool_result"
            assert tool_result_msg["content"][0]["tool_use_id"] == "tc_append_1"
            return SimpleNamespace(
                content=[_FakeTextBlock(text="done")],
                stop_reason="stop",
                reasoning_content="",
            )

    monkeypatch.setattr(article_author, "LLMClient", FakeLLMClient)

    article, tool_log, turns, finish_reason = article_author._call_deepseek_agent_loop(
        "system prompt",
        "user prompt",
        max_tokens=123,
        max_turns=3,
    )

    assert article == "# Title\nBody"
    assert turns == 2
    assert finish_reason == "stop"
    assert tool_log == [
        {
            "turn": 0,
            "kind": "append_article",
            "chunk_chars": len("# Title\nBody"),
            "running_total": len("# Title\nBody"),
        }
    ]
    client = FakeLLMClient.instances[0]
    assert client.kwargs["model"] == article_author.DEFAULT_MODEL
    assert client.kwargs["max_tokens"] == 123
    assert client.kwargs["tools"][0]["input_schema"]["required"] == ["url", "prompt"]
    assert client.calls[0]["caller"] == "publish_pipeline.article_author.turn_0"
    assert client.calls[0]["system"] == "system prompt"
    assert client.calls[0]["info_audit"] is False


def test_web_fetch_extracts_with_llmclient(monkeypatch) -> None:
    monkeypatch.setattr(article_author, "_ensure_the_company_api_key", lambda: None)
    monkeypatch.setattr(article_author, "_fetch_url_to_text", lambda url: f"page from {url}")

    class FakeLLMClient:
        instances: list["FakeLLMClient"] = []

        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs
            self.calls: list[dict[str, Any]] = []
            FakeLLMClient.instances.append(self)

        def call(self, **kwargs: Any) -> Any:
            self.calls.append(kwargs)
            return SimpleNamespace(
                content=[_FakeTextBlock(text="extracted facts")],
                stop_reason="stop",
                reasoning_content="",
            )

    monkeypatch.setattr(article_author, "LLMClient", FakeLLMClient)

    result = article_author._execute_web_fetch("https://example.test/post", "extract X")

    assert result == "extracted facts"
    client = FakeLLMClient.instances[0]
    assert client.kwargs == {
        "model": article_author.EXTRACT_MODEL,
        "max_tokens": 800,
        "tools": [],
    }
    assert client.calls[0]["caller"] == "publish_pipeline.article_author.web_fetch"
    assert client.calls[0]["info_audit"] is False
    assert "page from https://example.test/post" in client.calls[0]["messages"][0]["content"]


def test_article_author_has_no_active_llm_proxy_direct_call() -> None:
    source = Path(article_author.__file__).read_text(encoding="utf-8")

    assert "internal-llm-proxy.example.com/v1/chat/completions" not in source
    assert "THE_COMPANY_URL" not in source
    assert '"Authorization": f"Bearer' not in source
    assert "urllib.request.Request(THE_COMPANY_URL" not in source


def test_article_author_fan_in_keeps_dispatcher_semantics_without_list_literal() -> None:
    assert isinstance(article_author.ArticleAuthorWorker.FORMAT_IN, tuple)
    assert article_author.ArticleAuthorWorker.FORMAT_IN_MODE == "and"
    assert set(article_author.ArticleAuthorWorker.FORMAT_IN) == {
        "publish.request",
        "publish.commit_history",
        "publish.topic_briefs",
        "publish.topic_evidence",
        "publish.wiki_corpus",
    }
