"""Help assistant: tools, permissions and the chat endpoint with a fake model."""

import json
from collections.abc import Callable, Iterator
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import get_settings
from app.main import app
from app.models import AdPost, AppUser, SignalCard
from app.models.enums import Platform, Recipient, SignalOrigin, SignalStatus, Zone
from app.modules.assistant import knowledge, tools
from app.modules.assistant.router import get_llm_client, get_session_factory
from app.scope import build_scope
from tests.conftest import World, auth, make_object

CHAT = "/api/v1/assistant/chat"
GUIDE = Path(__file__).parent / "fixtures" / "assistant_guide"
QUESTION = {"messages": [{"role": "user", "content": "Как отправить карточку в ГАСК?"}]}


def run(db: Session, user: AppUser, name: str, args: object) -> dict[str, Any]:
    return tools.run_tool(name, args, db, user, build_scope(db, user))


def make_card(db: Session, obj_id: int, number: str, status: SignalStatus, recipient: Recipient | None) -> SignalCard:
    card = SignalCard(number=number, object_id=obj_id, status=status, origin=SignalOrigin.manual, recipient=recipient)
    db.add(card)
    db.flush()
    return card


# ---------------------------------------------------------------- tools


def test_gask_gets_no_staff_tools(world: World, db: Session) -> None:
    gask = world.users["gask"]
    names = {schema["function"]["name"] for schema in tools.tool_schemas(gask)}
    assert names == {"search_guide", "list_signals"}
    assert "error" in run(db, gask, "search_objects", {"query": "x"})
    assert "error" in run(db, gask, "work_summary", {})
    assert "error" in run(db, gask, "no_such_tool", {})
    staff = {schema["function"]["name"] for schema in tools.tool_schemas(world.users["mio_ust"])}
    assert staff == set(tools.TOOLS)


def test_search_objects_is_limited_to_the_scope(world: World, db: Session) -> None:
    make_object(db, world.ust, "ЖК Нурлы Усть", score=40)
    make_object(db, world.semey, "ЖК Нурлы Семей")
    result = run(db, world.users["mio_ust"], "search_objects", {"query": "Нурлы"})
    assert [item["name"] for item in result["objects"]] == ["ЖК Нурлы Усть"]
    assert result["objects"][0]["url"].startswith("/objects/")
    both = run(db, world.users["admin"], "search_objects", {"query": "Нурлы"})
    assert len(both["objects"]) == 2


def test_search_objects_by_zone_without_a_query(world: World, db: Session) -> None:
    make_object(db, world.ust, "ЖК Красный", score=70, zone=Zone.red)
    make_object(db, world.ust, "ЖК Зелёный", score=5, zone=Zone.green)
    result = run(db, world.users["mio_ust"], "search_objects", {"zone": "red"})
    assert [item["name"] for item in result["objects"]] == ["ЖК Красный"]
    assert tools.label("search_objects", {"zone": "red"}, "ru") == "Ищу объекты"


def test_get_object_outside_the_scope_is_not_found(world: World, db: Session) -> None:
    obj = make_object(db, world.ust, "ЖК Нурлы")
    assert run(db, world.users["mio_semey"], "get_object", {"object_id": obj.id}) == {"error": "not_found"}
    assert run(db, world.users["mio_ust"], "get_object", {"object_id": 10**9}) == {"error": "not_found"}
    found = run(db, world.users["mio_ust"], "get_object", {"object_id": obj.id})
    assert found["name"] == "ЖК Нурлы" and found["url"] == f"/objects/{obj.id}"


def test_bad_arguments_return_an_error(world: World, db: Session) -> None:
    mio = world.users["mio_ust"]
    assert "error" in run(db, mio, "get_object", {"object_id": "abc"})
    assert "error" in run(db, mio, "get_object", {})
    assert "error" in run(db, mio, "search_objects", {"query": "x", "zone": "purple"})
    assert "error" in run(db, mio, "search_objects", ["not", "an", "object"])
    assert "error" in run(db, mio, "list_signals", {"status": 5})


def test_list_signals_follows_visibility(world: World, db: Session) -> None:
    ust = make_object(db, world.ust, "ЖК Усть")
    other = make_object(db, world.semey, "ЖК Семей")
    make_card(db, ust.id, "SAQ-T-1", SignalStatus.requires_confirmation, None)
    make_card(db, ust.id, "SAQ-T-2", SignalStatus.sent, Recipient.gask)
    make_card(db, ust.id, "SAQ-T-3", SignalStatus.sent, Recipient.law_enforcement)
    make_card(db, other.id, "SAQ-T-4", SignalStatus.sent, Recipient.gask)

    def numbers(user: str, **args: object) -> set[str]:
        return {item["number"] for item in run(db, world.users[user], "list_signals", args)["signals"]}

    assert numbers("mio_ust") == {"SAQ-T-1", "SAQ-T-2", "SAQ-T-3"}
    assert numbers("mio_ust", status="sent") == {"SAQ-T-2", "SAQ-T-3"}
    assert numbers("gask") == {"SAQ-T-2"}
    assert numbers("admin") == {"SAQ-T-1", "SAQ-T-2", "SAQ-T-3", "SAQ-T-4"}
    assert numbers("mio_semey", object_id=ust.id) == set()


def test_search_ads_and_summary(world: World, db: Session) -> None:
    obj = make_object(db, world.ust, "ЖК Нурлы", score=70, zone="red")
    db.add(AdPost(platform=Platform.telegram, territory_id=world.ust.id, object_id=obj.id, text="Бронь квартиры " * 40))
    db.add(AdPost(platform=Platform.telegram, territory_id=world.semey.id, text="Бронь в Семее"))
    db.flush()
    ads = run(db, world.users["mio_ust"], "search_ads", {"query": "бронь"})["ads"]
    assert len(ads) == 1 and len(ads[0]["text"]) <= tools.MAX_TEXT_CHARS
    assert ads[0]["url"].startswith("/ads?ad=") and ads[0]["object"]["name"] == "ЖК Нурлы"

    summary = run(db, world.users["mio_ust"], "work_summary", {})
    assert summary["zones"]["red"] == 1 and summary["zones"]["total"] == 1
    assert summary["signals"]["sent"] == 0


def test_label_in_both_languages() -> None:
    assert tools.label("search_objects", {"query": "Нурлы"}, "ru") == "Ищу объекты: Нурлы"
    assert "Нурлы" in tools.label("search_objects", {"query": "Нурлы"}, "kk")
    assert tools.label("search_objects", {}, "ru") == "Ищу объекты"


# ---------------------------------------------------------------- chat


class FakeModel:
    """An OpenAI-compatible endpoint: `script` has one list of SSE events per request."""

    def __init__(self, script: list[list[dict[str, Any] | str]]) -> None:
        self.script = script
        self.requests: list[dict[str, Any]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(json.loads(request.content))
        events = self.script[min(len(self.requests), len(self.script)) - 1]
        body = "".join(f"data: {e if isinstance(e, str) else json.dumps(e)}\n\n" for e in events)
        return httpx.Response(200, content=body.encode())


def say(*parts: str) -> list[dict[str, Any] | str]:
    return [*({"choices": [{"delta": {"content": part}}]} for part in parts), "[DONE]"]


def ask_tool(name: str, arguments: str) -> list[dict[str, Any] | str]:
    call = {"index": 0, "id": "call_1", "function": {"name": name, "arguments": arguments}}
    return [{"choices": [{"delta": {"tool_calls": [call]}}]}, "[DONE]"]


@pytest.fixture
def use_model(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Callable[[FakeModel], None]]:
    """The stream gets the transactional test session and a client wired to the fake model."""
    monkeypatch.setattr(knowledge, "GUIDE_DIR", GUIDE)
    knowledge.guide_index.cache_clear()
    app.dependency_overrides[get_session_factory] = lambda: lambda: nullcontext(db)

    def install(model: FakeModel) -> None:
        http = httpx.Client(transport=httpx.MockTransport(model.handler))
        app.dependency_overrides[get_llm_client] = lambda: http

    yield install
    knowledge.guide_index.cache_clear()


def events(response: httpx.Response) -> list[dict[str, Any]]:
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-accel-buffering"] == "no"
    frames = [frame for frame in response.text.split("\n\n") if frame]
    assert all(frame.startswith("data: ") for frame in frames)
    return [json.loads(frame[len("data: ") :]) for frame in frames]


def test_chat_runs_the_tool_and_streams_the_answer(
    world: World, db: Session, client: TestClient, use_model: Callable[[FakeModel], None]
) -> None:
    obj = make_object(db, world.ust, "ЖК Нурлы")
    model = FakeModel([ask_tool("search_objects", '{"query": "Нурлы"}'), say("Это ", f"[ЖК Нурлы](/objects/{obj.id})")])
    use_model(model)
    body = {**QUESTION, "page": {"path": "/signals"}, "language": "ru"}

    response = client.post(CHAT, json=body, headers=auth(world.users["mio_ust"]))

    sequence = events(response)
    assert [e["type"] for e in sequence] == ["sources", "tool", "delta", "delta", "done"]
    assert sequence[0]["sources"][0] == {
        "id": "signals#1",
        "title": "Сигнальные карточки — Как отправить карточку в ГАСК",
        "page": "/signals",
    }
    assert sequence[1] == {"type": "tool", "name": "search_objects", "label": "Ищу объекты: Нурлы"}
    assert "".join(e["text"] for e in sequence if e["type"] == "delta") == f"Это [ЖК Нурлы](/objects/{obj.id})"

    first, second = model.requests
    assert first["stream"] is True and len(first["tools"]) == len(tools.TOOLS)
    assert first["messages"][0]["role"] == "system" and "/signals" in first["messages"][0]["content"]
    assert "Как отправить карточку" in first["messages"][0]["content"]
    assistant, tool_message = second["messages"][-2:]
    assert assistant["tool_calls"][0]["id"] == "call_1"
    assert tool_message["role"] == "tool" and tool_message["tool_call_id"] == "call_1"
    assert "ЖК Нурлы" in tool_message["content"] and f"/objects/{obj.id}" in tool_message["content"]


def test_chat_puts_the_open_object_into_the_prompt_for_staff_only(
    world: World, db: Session, client: TestClient, use_model: Callable[[FakeModel], None]
) -> None:
    obj = make_object(db, world.ust, "ЖК Секретный")
    page = {"path": f"/objects/{obj.id}", "entity": {"type": "object", "id": obj.id}}
    prompts = []
    for user in ("mio_ust", "gask", "mio_semey"):
        model = FakeModel([say("ок")])
        use_model(model)
        events(client.post(CHAT, json={**QUESTION, "page": page}, headers=auth(world.users[user])))
        prompts.append(model.requests[0]["messages"][0]["content"])
    assert "ЖК Секретный" in prompts[0]
    assert "ЖК Секретный" not in prompts[1]
    assert "ЖК Секретный" not in prompts[2]


def test_chat_gask_is_offered_only_its_tools(
    world: World, client: TestClient, use_model: Callable[[FakeModel], None]
) -> None:
    model = FakeModel([say("ок")])
    use_model(model)
    events(client.post(CHAT, json=QUESTION, headers=auth(world.users["gask"])))
    assert {t["function"]["name"] for t in model.requests[0]["tools"]} == {"search_guide", "list_signals"}


def test_chat_stops_after_too_many_tool_rounds(
    world: World, client: TestClient, use_model: Callable[[FakeModel], None], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "assistant_max_tool_rounds", 2)
    model = FakeModel([ask_tool("work_summary", "{}")])
    use_model(model)
    sequence = events(client.post(CHAT, json=QUESTION, headers=auth(world.users["mio_ust"])))
    assert [e["type"] for e in sequence] == ["sources", "tool", "tool", "error"]
    assert sequence[-1]["code"] == "too_many_tool_rounds"
    assert len(model.requests) == 3
    last = model.requests[-1]
    assert "tools" not in last and last["messages"][-1]["role"] == "system"


def test_chat_separates_rounds_and_marks_a_truncated_answer(
    world: World, client: TestClient, use_model: Callable[[FakeModel], None]
) -> None:
    thinking: list[dict[str, Any] | str] = [
        {"choices": [{"delta": {"content": "Сейчас поищу."}}]},
        *ask_tool("work_summary", "{}"),
    ]
    cut: list[dict[str, Any] | str] = [
        {"choices": [{"delta": {"content": "Итого"}, "finish_reason": "length"}]},
        "[DONE]",
    ]
    use_model(FakeModel([thinking, cut]))
    sequence = events(client.post(CHAT, json=QUESTION, headers=auth(world.users["mio_ust"])))
    text = "".join(e["text"] for e in sequence if e["type"] == "delta")
    assert text.startswith("Сейчас поищу.\n\nИтого") and "Ответ обрезан" in text
    assert sequence[-1] == {"type": "done"}


def test_chat_survives_bad_tool_arguments(
    world: World, client: TestClient, use_model: Callable[[FakeModel], None]
) -> None:
    model = FakeModel([ask_tool("get_object", "{not json"), say("Не получилось")])
    use_model(model)
    sequence = events(client.post(CHAT, json=QUESTION, headers=auth(world.users["mio_ust"])))
    assert sequence[-1] == {"type": "done"}
    assert "error" in json.loads(model.requests[1]["messages"][-1]["content"])


def test_chat_reports_model_failure_as_an_event(
    world: World, client: TestClient, use_model: Callable[[FakeModel], None]
) -> None:
    use_model(FakeModel([]))
    app.dependency_overrides[get_llm_client] = lambda: httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(500))
    )
    sequence = events(client.post(CHAT, json=QUESTION, headers=auth(world.users["mio_ust"])))
    assert [e["type"] for e in sequence] == ["sources", "error"]
    assert sequence[-1]["code"] == "llm_unavailable"
    assert "Bearer" not in json.dumps(sequence)


def test_chat_hides_unexpected_failures(
    world: World, client: TestClient, use_model: Callable[[FakeModel], None], monkeypatch: pytest.MonkeyPatch
) -> None:
    use_model(FakeModel([say("ок")]))

    def explode(*args: object, **kwargs: object) -> Iterator[str]:
        raise RuntimeError("secret internals")

    monkeypatch.setattr("app.modules.assistant.llm.stream_chat", explode)
    sequence = events(client.post(CHAT, json=QUESTION, headers=auth(world.users["mio_ust"])))
    assert sequence[-1]["code"] == "internal_error"
    assert "secret" not in json.dumps(sequence)


# ---------------------------------------------------------------- endpoints


def test_config(world: World, client: TestClient) -> None:
    response = client.get("/api/v1/assistant/config", headers=auth(world.users["gask"]))
    assert response.status_code == 200
    assert response.json() == {"enabled": True, "model": get_settings().assistant_model}


@pytest.mark.parametrize(
    "body",
    [
        {"messages": []},
        {"messages": [{"role": "assistant", "content": "hi"}]},
        {"messages": [{"role": "system", "content": "hi"}]},
        {"messages": [{"role": "user", "content": ""}]},
        {"messages": [{"role": "user", "content": "x" * 4001}]},
        {"messages": [{"role": "user", "content": "hi"}] * 21},
        {"messages": [{"role": "user", "content": "hi"}], "language": "en"},
        {"messages": [{"role": "user", "content": "hi"}], "page": {"path": "/" + "a" * 200}},
        {"messages": [{"role": "user", "content": "hi"}], "page": {"path": "/x", "entity": {"type": "user", "id": 1}}},
    ],
)
def test_chat_rejects_invalid_body(world: World, client: TestClient, body: dict[str, Any]) -> None:
    assert client.post(CHAT, json=body, headers=auth(world.users["mio_ust"])).status_code == 422


def test_endpoints_require_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/assistant/config").status_code == 401
    assert client.post(CHAT, json=QUESTION).status_code == 401


def test_zone_reasons_are_put_into_words() -> None:
    assert tools._zone_reason("score_0_24") == "Балл в диапазоне 0–24"
    assert tools._zone_reason("score_60_without_r1_r2").startswith("Балл 60+")
    assert "R1 и R2" in tools._zone_reason("r1_and_r2")
