from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from omnicompany.runtime.llm.structured import (
    DEFAULT_STRUCTURED_MODEL,
    DEFAULT_STRUCTURED_MODEL_ENV,
    StructuredJSONError,
    call_json,
    default_structured_model,
    parse_json_block,
    validate_json_schema,
)


class _TextBlock:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeClient:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def call(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        text = self._responses.pop(0)
        return SimpleNamespace(content=[_TextBlock(text)])


class _FakeFactory:
    def __init__(self, responses: list[str]) -> None:
        self.client = _FakeClient(responses)
        self.kwargs: dict[str, Any] | None = None

    def __call__(self, **kwargs: Any) -> _FakeClient:
        self.kwargs = kwargs
        return self.client


PLAN_SCHEMA = {
    "type": "object",
    "required": ["plans"],
    "properties": {
        "plans": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id"],
                "properties": {"id": {"type": "string"}},
            },
        },
    },
}


def test_parse_json_block_accepts_fenced_json() -> None:
    assert parse_json_block('```json\n{"ok": true}\n```') == {"ok": True}


def test_validate_json_schema_reports_nested_type_issue() -> None:
    issues = validate_json_schema({"plans": [{"id": 42}]}, PLAN_SCHEMA)
    assert any(issue.path == "$.plans[0].id" for issue in issues)


def test_call_json_parses_valid_json_and_disables_info_audit() -> None:
    factory = _FakeFactory(['prefix\n```json\n{"plans": [{"id": "p1"}]}\n```'])

    result = call_json(
        system="classify",
        user="input",
        schema=PLAN_SCHEMA,
        model="test-model",
        caller="tests.structured",
        client_factory=factory,
    )

    assert result == {"plans": [{"id": "p1"}]}
    assert factory.kwargs == {"model": "test-model", "max_tokens": 8000}
    assert factory.client.calls[0]["info_audit"] is False
    assert factory.client.calls[0]["caller"] == "tests.structured"


def test_call_json_role_uses_role_without_default_model() -> None:
    factory = _FakeFactory(['{"plans": [{"id": "p1"}]}'])

    result = call_json(
        system="classify",
        user="input",
        schema=PLAN_SCHEMA,
        role="runtime_main",
        client_factory=factory,
    )

    assert result == {"plans": [{"id": "p1"}]}
    assert factory.kwargs == {"max_tokens": 8000, "role": "runtime_main"}


def test_call_json_retries_once_after_schema_failure() -> None:
    factory = _FakeFactory([
        '{"plans": [{"id": 42}]}',
        '{"plans": [{"id": "fixed"}]}',
    ])

    result = call_json(
        system="classify",
        user="input",
        schema=PLAN_SCHEMA,
        model="test-model",
        client_factory=factory,
    )

    assert result == {"plans": [{"id": "fixed"}]}
    assert len(factory.client.calls) == 2
    second_messages = factory.client.calls[1]["messages"]
    assert "previous response was not valid JSON" in second_messages[-1]["content"]


def test_call_json_raises_after_exhausting_correction_retry() -> None:
    factory = _FakeFactory([
        '{"plans": [{"id": 42}]}',
        '{"plans": [{"id": 99}]}',
    ])

    with pytest.raises(StructuredJSONError):
        call_json(
            system="classify",
            user="input",
            schema=PLAN_SCHEMA,
            model="test-model",
            client_factory=factory,
        )


def test_default_structured_model_uses_env_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DEFAULT_STRUCTURED_MODEL_ENV, "glm-test")
    assert default_structured_model() == "glm-test"

    monkeypatch.delenv(DEFAULT_STRUCTURED_MODEL_ENV, raising=False)
    assert default_structured_model() == DEFAULT_STRUCTURED_MODEL
