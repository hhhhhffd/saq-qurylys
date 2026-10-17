from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

MAX_MESSAGES = 20
MAX_MESSAGE_CHARS = 4000
MAX_PATH_CHARS = 200


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class PageEntity(BaseModel):
    type: Literal["object", "signal", "ad", "vision_session"]
    id: int


class PageContext(BaseModel):
    path: str = Field(max_length=MAX_PATH_CHARS)
    entity: PageEntity | None = None


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=MAX_MESSAGES)
    page: PageContext | None = None
    language: Literal["ru", "kk"] = "ru"

    @model_validator(mode="after")
    def _last_is_user(self) -> Self:
        if self.messages[-1].role != "user":
            raise ValueError("the last message must be from the user")
        return self


class AssistantConfig(BaseModel):
    enabled: bool
    model: str
