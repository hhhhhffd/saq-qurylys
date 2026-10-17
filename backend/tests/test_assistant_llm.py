"""Streaming client of the assistant and its guide search; no database needed."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.config import get_settings
from app.modules.assistant import knowledge
from app.modules.assistant.llm import AssistantLlmError, ToolCall, Truncated, stream_chat

GUIDE = Path(__file__).parent / "fixtures" / "assistant_guide"


def sse(*events: dict[str, Any] | str) -> bytes:
    lines = [f"data: {event if isinstance(event, str) else json.dumps(event)}\n\n" for event in events]
    return "".join(lines).encode()


def content(text: str) -> dict[str, Any]:
    return {"choices": [{"delta": {"content": text}}]}


def tool_delta(*deltas: dict[str, Any]) -> dict[str, Any]:
    return {"choices": [{"delta": {"tool_calls": list(deltas)}}]}


def collect(body: bytes, *, status: int = 200) -> list[str | ToolCall | Truncated]:
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(status, content=body)))
    return list(stream_chat([{"role": "user", "content": "hi"}], [], client=client))


def test_text_deltas_in_order() -> None:
    assert collect(sse(content("При"), content("вет"), "[DONE]")) == ["При", "вет"]


def test_tool_call_arguments_are_joined_by_index() -> None:
    body = sse(
        tool_delta({"index": 0, "id": "c1", "function": {"name": "search_objects", "arguments": ""}}),
        tool_delta({"index": 0, "function": {"arguments": '{"query": '}}),
        tool_delta({"index": 0, "function": {"arguments": '"Нурлы"}'}}),
        tool_delta({"index": 1, "id": "c2", "function": {"name": "work_summary", "arguments": "{}"}}),
        "[DONE]",
    )
    assert collect(body) == [
        ToolCall("c1", "search_objects", '{"query": "Нурлы"}'),
        ToolCall("c2", "work_summary", "{}"),
    ]


def test_tool_call_sent_whole_like_ollama() -> None:
    delta = {
        "id": "call_x",
        "index": 0,
        "type": "function",
        "function": {"name": "get_object", "arguments": '{"object_id": 3}'},
    }
    assert collect(sse(tool_delta(delta), "[DONE]")) == [ToolCall("call_x", "get_object", '{"object_id": 3}')]


def test_tool_calls_without_index_are_separate_calls() -> None:
    body = sse(
        tool_delta({"function": {"name": "work_summary", "arguments": "{}"}}),
        tool_delta({"function": {"name": "list_signals", "arguments": "{}"}}),
        "[DONE]",
    )
    assert [call.name for call in collect(body) if isinstance(call, ToolCall)] == ["work_summary", "list_signals"]


def test_think_blocks_are_removed_also_across_chunks() -> None:
    body = sse(content("<thi"), content("nk>скрыто"), content(" ещё</th"), content("ink>Ответ"), "[DONE]")
    assert "".join(str(item) for item in collect(body)) == "Ответ"


def test_text_that_only_looks_like_a_tag_is_kept() -> None:
    assert "".join(str(item) for item in collect(sse(content("a <"), content("b"), "[DONE]"))) == "a <b"


def test_http_error_is_llm_unavailable() -> None:
    with pytest.raises(AssistantLlmError) as error:
        collect(b"boom", status=500)
    assert error.value.code == "llm_unavailable"


def test_transport_error_is_llm_unavailable() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    client = httpx.Client(transport=httpx.MockTransport(refuse))
    with pytest.raises(AssistantLlmError) as error:
        list(stream_chat([], [], client=client))
    assert error.value.code == "llm_unavailable"


@pytest.mark.parametrize("body", [b"<html>not an event stream</html>", b"data: {not json}\n\n", sse({"choices": "x"})])
def test_garbage_is_llm_bad_response(body: bytes) -> None:
    with pytest.raises(AssistantLlmError) as error:
        collect(body)
    assert error.value.code == "llm_bad_response"


def test_request_shape_and_secret_header(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=sse(content("ok"), "[DONE]"))

    settings = get_settings()
    monkeypatch.setattr(settings, "assistant_base_url", "http://model.test/v1/")
    monkeypatch.setattr(settings, "assistant_api_key", "")
    monkeypatch.setattr(settings, "assistant_reasoning_effort", "none")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    list(stream_chat([{"role": "user", "content": "hi"}], [], client=client))
    monkeypatch.setattr(settings, "assistant_api_key", "secret-key")
    monkeypatch.setattr(settings, "assistant_reasoning_effort", "")
    tools = [{"type": "function", "function": {"name": "t"}}]
    list(stream_chat([{"role": "user", "content": "hi"}], tools, client=client))

    first, second = seen
    assert str(first.url) == "http://model.test/v1/chat/completions"
    assert "authorization" not in first.headers
    body = json.loads(first.content)
    assert body["stream"] is True and body["reasoning_effort"] == "none" and "tools" not in body
    assert second.headers["authorization"] == "Bearer secret-key"
    body = json.loads(second.content)
    assert "reasoning_effort" not in body and body["tools"] == tools


# ---------------------------------------------------------------- guide search


def test_guide_is_split_into_sections() -> None:
    index = knowledge.load_index(GUIDE)
    by_id = {chunk.id: chunk for chunk in index.chunks}
    assert by_id["signals#0"].title == "Сигнальные карточки"
    assert by_id["signals#1"].title == "Сигнальные карточки — Как отправить карточку в ГАСК"
    assert by_id["signals#1"].page == "/signals"
    assert by_id["map#1"].page is None
    assert "page:" not in by_id["signals#0"].text


def test_guide_search_matches_inflected_words() -> None:
    index = knowledge.load_index(GUIDE)
    found = index.search("Как отправить карточку?", 4)
    assert found[0].id == "signals#1"


def test_guide_search_returns_only_matching_chunks() -> None:
    index = knowledge.load_index(GUIDE)
    assert index.search("слои", 4)[0].id == "map#1"
    assert index.search("квантовая хромодинамика", 4) == []
    assert len(index.search("карточка", 1)) == 1
