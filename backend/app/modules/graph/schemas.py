from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints

from app.models.enums import Platform, Zone

NodeType = Literal["developer", "object", "phone", "account", "ad"]
EdgeType = Literal["developer_object", "owner_phone", "owner_account", "ad_object", "ad_phone", "ad_account"]
FindingKind = Literal["shared_phone", "shared_account"]


class GraphNode(BaseModel):
    """`id` is `<type>:<key>`: `object:12`, `phone:+77000000101`, `account:instagram/handle`. `ref_id` is the
    database id of a developer, object or ad."""

    id: str
    type: NodeType
    label: str
    ref_id: int | None = None
    zone: Zone | None = None
    is_demo: bool | None = None
    platform: Platform | None = None


class GraphEdge(BaseModel):
    source: str
    target: str
    type: EdgeType


class GraphFinding(BaseModel):
    """A phone or an account that ties together objects of different developers. `value` is the key of the node
    (`+77000000101` or `instagram/handle`)."""

    kind: FindingKind
    value: str
    label: str
    developer_ids: list[int]
    object_ids: list[int]


class Graph(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    findings: list[GraphFinding]
    truncated: bool


class SourceSuggestion(BaseModel):
    platform: Platform
    handle: str
    url: str
    posts_count: int
    object_ids: list[int]
    last_seen_at: datetime | None


class SuggestionDismiss(BaseModel):
    platform: Platform
    handle: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
