"""Streaming client of an OpenAI-compatible `/chat/completions` (Ollama, Gemini, Groq, ...).

Sync on purpose: the chat handler streams from a sync generator, which Starlette runs in the thread pool."""

import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

THINK_OPEN = "<think>"
THINK_CLOSE = "</think>"
TEMPERATURE = 0.2


class AssistantLlmError(Exception):
    """`llm_unavailable`: transport or HTTP failure; `llm_bad_response`: the answer cannot be parsed."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # JSON text as the model wrote it; the caller parses it


class _ThinkFilter:
    """Drops `<think>...</think>` from streamed content. A tag may be split between chunks, so a tail that
    could still become a tag is held back until the next chunk."""

    def __init__(self) -> None:
        self.inside = False
        self.pending = ""

    def feed(self, text: str) -> str:
        data = self.pending + text
        self.pending = ""
        visible: list[str] = []
        while data:
            tag = THINK_CLOSE if self.inside else THINK_OPEN
            position = data.find(tag)
            if position >= 0:
                if not self.inside:
                    visible.append(data[:position])
                data = data[position + len(tag) :]
                self.inside = not self.inside
                continue
            held = next((n for n in range(min(len(tag) - 1, len(data)), 0, -1) if tag.startswith(data[-n:])), 0)
            if not self.inside:
                visible.append(data[: len(data) - held])
            self.pending = data[len(data) - held :]
            break
        return "".join(visible)

    def flush(self) -> str:
        tail = "" if self.inside else self.pending
        self.pending = ""
        return tail


def _request_body(messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
    settings = get_settings()
    body: dict[str, Any] = {
        "model": settings.assistant_model,
        "messages": messages,
        "stream": True,
        "temperature": TEMPERATURE,
    }
    if tools:
        body["tools"] = tools
    if settings.assistant_reasoning_effort:
        body["reasoning_effort"] = settings.assistant_reasoning_effort
    return body


def _merge_tool_calls(calls: list[ToolCall], by_index: dict[int, ToolCall], deltas: list[dict[str, Any]]) -> None:
    """OpenAI and Groq stream a call in pieces with the same `index`; Ollama sends it whole; Gemini may omit the
    index, then every delta is a call of its own."""
    for delta in deltas:
        function = delta.get("function") or {}
        arguments = function.get("arguments") or ""
        if not isinstance(arguments, str):
            arguments = json.dumps(arguments, ensure_ascii=False)
        index = delta.get("index")
        call = by_index.get(index) if isinstance(index, int) else None
        if call is None:
            call = ToolCall(id=delta.get("id") or f"call_{len(calls)}", name="", arguments="")
            calls.append(call)
            if isinstance(index, int):
                by_index[index] = call
        call.name += function.get("name") or ""
        call.arguments += arguments


def stream_chat(
    messages: list[dict[str, Any]], tools: list[dict[str, Any]], *, client: httpx.Client | None = None
) -> Iterator[str | ToolCall]:
    """Yields the text deltas of the answer as they arrive, then the tool calls the model asked for (if any)."""
    settings = get_settings()
    headers = {"Authorization": f"Bearer {settings.assistant_api_key}"} if settings.assistant_api_key else {}
    url = f"{settings.assistant_base_url.rstrip('/')}/chat/completions"
    owns_client = client is None
    http = client or httpx.Client(timeout=settings.assistant_timeout_s)
    think = _ThinkFilter()
    calls: list[ToolCall] = []
    by_index: dict[int, ToolCall] = {}
    chunks = 0
    try:
        with http.stream("POST", url, json=_request_body(messages, tools), headers=headers) as response:
            if response.status_code >= 400:
                logger.warning("Assistant model answered HTTP %s", response.status_code)
                raise AssistantLlmError("llm_unavailable")
            for line in response.iter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[len("data:") :].strip()
                if payload == "[DONE]":
                    break
                try:
                    choices = json.loads(payload)["choices"]
                    delta = choices[0]["delta"] if choices else {}
                    content = delta.get("content")
                    tool_deltas = delta.get("tool_calls")
                except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
                    raise AssistantLlmError("llm_bad_response") from exc
                chunks += 1
                if isinstance(content, str) and content:
                    text = think.feed(content)
                    if text:
                        yield text
                if isinstance(tool_deltas, list):
                    _merge_tool_calls(calls, by_index, tool_deltas)
    except httpx.HTTPError as exc:
        logger.warning("Assistant model request failed: %s", type(exc).__name__)
        raise AssistantLlmError("llm_unavailable") from exc
    except UnicodeDecodeError as exc:
        raise AssistantLlmError("llm_bad_response") from exc
    finally:
        if owns_client:
            http.close()
    if not chunks:  # not an event stream at all
        raise AssistantLlmError("llm_bad_response")
    tail = think.flush()
    if tail:
        yield tail
    yield from (call for call in calls if call.name)
