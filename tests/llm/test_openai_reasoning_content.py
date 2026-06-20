from __future__ import annotations

from types import SimpleNamespace

from omnicompany.runtime.llm.llm import LLMClient


def test_anthropic_to_openai_preserves_reasoning_content_for_tool_turn() -> None:
    client = LLMClient(model="deepseek-v4-pro", api_key="test-key")

    converted = client._anthropic_msgs_to_openai(
        [
            {
                "role": "assistant",
                "reasoning_content": "keep this reasoning",
                "content": [
                    {"type": "text", "text": "I will call a tool."},
                    {
                        "type": "tool_use",
                        "id": "tc_1",
                        "name": "append_article",
                        "input": {"content": "# Title"},
                    },
                ],
            }
        ]
    )

    assert converted == [
        {
            "role": "assistant",
            "content": "I will call a tool.",
            "tool_calls": [
                {
                    "id": "tc_1",
                    "type": "function",
                    "function": {
                        "name": "append_article",
                        "arguments": '{"content": "# Title"}',
                    },
                }
            ],
            "reasoning_content": "keep this reasoning",
        }
    ]


def test_openai_stream_collects_reasoning_content() -> None:
    client = LLMClient(model="deepseek-v4-pro", api_key="test-key")
    captured_kwargs = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured_kwargs.update(kwargs)
            usage = SimpleNamespace(prompt_tokens=7, completion_tokens=5)
            return iter(
                [
                    SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                delta=SimpleNamespace(
                                    content="answer ",
                                    reasoning_content="think ",
                                    tool_calls=None,
                                ),
                                finish_reason=None,
                            )
                        ],
                        model="deepseek-v4-pro",
                        usage=None,
                    ),
                    SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                delta=SimpleNamespace(
                                    content="done",
                                    reasoning_content="more",
                                    tool_calls=None,
                                ),
                                finish_reason="stop",
                            )
                        ],
                        model="deepseek-v4-pro",
                        usage=usage,
                    ),
                ]
            )

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=FakeCompletions()),
    )

    response = client._call_openai_with(
        fake_client,
        "deepseek-v4-pro",
        [{"role": "user", "content": "hello"}],
        "system",
        "",
    )

    assert captured_kwargs["stream"] is True
    assert response.reasoning_content == "think more"
    assert response.content[0].text == "answer done"
    assert response.stop_reason == "stop"
    assert response.usage.input_tokens == 7
    assert response.usage.output_tokens == 5
