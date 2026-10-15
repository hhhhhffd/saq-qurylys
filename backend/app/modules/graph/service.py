"""Link graph (SPEC 10.3): developers, objects, phones, accounts and publications joined by what they share.

The whole graph of the user's scope is built in memory from a few queries; a focused view (one object or one
developer) is cut out of it, and a view that is too large is cut down to `MAX_NODES`.
"""

import heapq
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models import AdPost, ConstructionObject, Developer, LinkedEntity, SourceAccount, Territory
from app.models.enums import LinkedEntityKind, Platform
from app.modules.ads.urls import detect_platform, handle_from_url
from app.modules.developers.service import visible_developers
from app.modules.graph.schemas import EdgeType, Graph, GraphEdge, GraphFinding, GraphNode
from app.modules.settings.service import load_settings
from app.phones import normalize_phone
from app.scope import TerritoryScope

MAX_NODES = 400
# Publications older than the analysis window still show how an account or a phone was used.
MIN_AD_WINDOW_DAYS = 90
AD_LABEL_CHARS = 60
# Platforms whose links name a profile worth watching; a link to any other site is not an account.
SOCIAL_PLATFORMS = frozenset({Platform.instagram, Platform.telegram, Platform.tiktok})
# First path segments of t.me links that are not channels.
_NOT_A_HANDLE = frozenset({"share", "joinchat", "addlist", "addstickers", "proxy", "iv"})

ad_recency = func.coalesce(AdPost.published_at, AdPost.captured_at, AdPost.created_at)

OWNERS = frozenset({"developer", "object"})
IDENTIFIERS = frozenset({"phone", "account"})
# Truncation keeps developers and objects first, then phones and accounts, then publications.
_TIER = {"developer": 0, "object": 0, "phone": 1, "account": 1, "ad": 2}


def ad_window_start(session: Session) -> datetime:
    return datetime.now(UTC) - timedelta(days=max(MIN_AD_WINDOW_DAYS, load_settings(session).ad_window_days))


def normalize_account(value: str) -> tuple[Platform, str] | None:
    """Platform and lowercase handle of an account given as a profile URL, a host or a bare `@handle`.

    A bare handle names no platform, so it can only match the same bare handle.
    """
    text = value.strip()
    if text.startswith("@") or ("." not in text and "/" not in text):
        bare = text.removeprefix("@").lower()
        return (Platform.other, bare) if bare else None
    url = text if "://" in text else f"https://{text}"
    platform = detect_platform(url)
    handle = handle_from_url(platform, url)
    if handle is None or (platform is Platform.telegram and handle in _NOT_A_HANDLE):
        return None
    return platform, handle


def account_key(platform: Platform, handle: str) -> str:
    return f"account:{platform.value}/{handle}"


def _kind(key: str) -> str:
    return key.partition(":")[0]


@dataclass
class _Graph:
    nodes: dict[str, GraphNode] = field(default_factory=dict)
    edges: set[tuple[str, str, EdgeType]] = field(default_factory=set)
    adj: defaultdict[str, set[str]] = field(default_factory=lambda: defaultdict(set))

    def add(self, node: GraphNode) -> str:
        self.nodes.setdefault(node.id, node)
        self.adj.setdefault(node.id, set())
        return node.id

    def link(self, source: str, target: str, kind: EdgeType) -> None:
        if source in self.nodes and target in self.nodes:
            self.edges.add((source, target, kind))
            self.adj[source].add(target)
            self.adj[target].add(source)

    def phone(self, raw: str, *, normalize: bool = True) -> str:
        value = (normalize_phone(raw) if normalize else None) or raw.strip()
        return self.add(GraphNode(id=f"phone:{value}", type="phone", label=value))

    def account(self, platform: Platform, handle: str) -> str:
        label = f"@{handle}" if platform in SOCIAL_PLATFORMS else handle
        return self.add(GraphNode(id=account_key(platform, handle), type="account", label=label, platform=platform))


def _object_ids(scope: TerritoryScope) -> Select[int]:
    return scope.restrict(select(ConstructionObject.id), ConstructionObject.territory_id)


def _developer_ids(scope: TerritoryScope) -> Select[int]:
    return select(Developer.id).where(visible_developers(scope))


def _owner_key(object_id: int | None, developer_id: int | None) -> str:
    return f"object:{object_id}" if object_id is not None else f"developer:{developer_id}"


def _add_owners(graph: _Graph, session: Session, scope: TerritoryScope) -> None:
    developers = select(Developer.id, Developer.name, Developer.phones).where(Developer.id.in_(_developer_ids(scope)))
    for developer_id, name, phones in session.execute(developers):
        key = graph.add(GraphNode(id=f"developer:{developer_id}", type="developer", label=name, ref_id=developer_id))
        for phone in phones:
            graph.link(key, graph.phone(phone), "owner_phone")
    objects = scope.restrict(
        select(
            ConstructionObject.id,
            ConstructionObject.name,
            ConstructionObject.developer_id,
            ConstructionObject.zone,
            ConstructionObject.is_demo,
        ),
        ConstructionObject.territory_id,
    )
    for object_id, name, owner_id, zone, is_demo in session.execute(objects):
        key = graph.add(
            GraphNode(id=f"object:{object_id}", type="object", label=name, ref_id=object_id, zone=zone, is_demo=is_demo)
        )
        if owner_id is not None:
            graph.link(f"developer:{owner_id}", key, "developer_object")


def _add_linked_entities(graph: _Graph, session: Session, scope: TerritoryScope) -> None:
    entities = select(LinkedEntity.object_id, LinkedEntity.developer_id, LinkedEntity.kind, LinkedEntity.value).where(
        LinkedEntity.kind.in_((LinkedEntityKind.phone, LinkedEntityKind.ad_account, LinkedEntityKind.website)),
        or_(LinkedEntity.object_id.in_(_object_ids(scope)), LinkedEntity.developer_id.in_(_developer_ids(scope))),
    )
    for object_id, developer_id, kind, value in session.execute(entities):
        owner = _owner_key(object_id, developer_id)
        if kind is LinkedEntityKind.phone:
            graph.link(owner, graph.phone(value), "owner_phone")
        elif (account := normalize_account(value)) is not None:
            graph.link(owner, graph.account(*account), "owner_account")


def _ads_stmt(session: Session, scope: TerritoryScope) -> Select[Any]:
    return scope.restrict(
        select(
            AdPost.id,
            AdPost.object_id,
            AdPost.phones,
            AdPost.links,
            AdPost.source_account_id,
            AdPost.platform,
            AdPost.is_demo,
            func.left(AdPost.text, AD_LABEL_CHARS),
            AdPost.url,
        ),
        AdPost.territory_id,
    ).where(ad_recency >= ad_window_start(session))


def _add_source_accounts(graph: _Graph, session: Session, scope: TerritoryScope) -> dict[int, str]:
    """Accounts of someone in the scope, and those the publications of the scope come from."""
    sources = select(
        SourceAccount.id,
        SourceAccount.platform,
        SourceAccount.handle,
        SourceAccount.object_id,
        SourceAccount.developer_id,
    ).where(
        or_(
            SourceAccount.object_id.in_(_object_ids(scope)),
            SourceAccount.developer_id.in_(_developer_ids(scope)),
            SourceAccount.id.in_(_ads_stmt(session, scope).with_only_columns(AdPost.source_account_id)),
        )
    )
    keys: dict[int, str] = {}
    for source_id, platform, handle, object_id, developer_id in session.execute(sources):
        keys[source_id] = key = graph.account(platform, handle.lower())
        if object_id is not None:
            graph.link(_owner_key(object_id, None), key, "owner_account")
        if developer_id is not None:
            graph.link(_owner_key(None, developer_id), key, "owner_account")
    return keys


def _add_ads(graph: _Graph, session: Session, scope: TerritoryScope, source_keys: dict[int, str]) -> None:
    for ad_id, object_id, phones, links, source_id, platform, is_demo, snippet, url in session.execute(
        _ads_stmt(session, scope)
    ):
        key = graph.add(
            GraphNode(
                id=f"ad:{ad_id}",
                type="ad",
                label=" ".join(snippet.split()) if snippet and snippet.strip() else url or f"#{ad_id}",
                ref_id=ad_id,
                is_demo=is_demo,
                platform=platform,
            )
        )
        if object_id is not None:
            graph.link(key, f"object:{object_id}", "ad_object")
        for phone in phones:
            graph.link(key, graph.phone(phone, normalize=False), "ad_phone")  # stored in E.164 already
        if source_id in source_keys:
            graph.link(key, source_keys[source_id], "ad_account")
        for link in links:
            # A link to a site counts only when that site is an account of someone already: most links are generic.
            if (account := normalize_account(link)) is not None and (
                account[0] in SOCIAL_PLATFORMS or account_key(*account) in graph.nodes
            ):
                graph.link(key, graph.account(*account), "ad_account")


def _load(session: Session, scope: TerritoryScope) -> _Graph:
    """Every developer, object, phone, account and recent publication of the scope, with their links."""
    graph = _Graph()
    _add_owners(graph, session, scope)
    _add_linked_entities(graph, session, scope)
    _add_ads(graph, session, scope, _add_source_accounts(graph, session, scope))
    return graph


def territory_scope(session: Session, scope: TerritoryScope, territory_id: int) -> TerritoryScope:
    """The territory with everything below it, within what the user may see."""
    subtree = select(Territory.id).where(Territory.id == territory_id).cte("subtree", recursive=True)
    subtree = subtree.union_all(select(Territory.id).join(subtree, Territory.parent_id == subtree.c.id))
    ids = frozenset(session.scalars(select(subtree.c.id)))
    return TerritoryScope(ids=ids if scope.ids is None else ids & scope.ids)


# ---------------------------------------------------------------- views


def _reach(adj: defaultdict[str, set[str]], key: str, wanted: frozenset[str]) -> set[str]:
    """Neighbours of the wanted kinds: next to the node, or next to a publication that is next to it."""
    found: set[str] = set()
    for neighbour in adj[key]:
        kind = _kind(neighbour)
        if kind in wanted:
            found.add(neighbour)
        elif kind == "ad":
            found.update(other for other in adj[neighbour] if _kind(other) in wanted)
    return found


def _family(adj: defaultdict[str, set[str]], owners: set[str]) -> set[str]:
    for _ in range(2):  # an object -> its developer -> the other objects of that developer
        owners = owners | {n for owner in owners for n in adj[owner] if _kind(n) in OWNERS}
    return owners


def _neighbourhood(adj: defaultdict[str, set[str]], seeds: set[str]) -> set[str]:
    """Two hops: the seed with its developer and their other objects; every phone and account of these;
    whoever else holds them, with their developers and objects; the publications around all of it."""
    owners = _family(adj, seeds)
    identifiers = set[str]().union(*(_reach(adj, owner, IDENTIFIERS) for owner in owners))
    owners = _family(adj, owners.union(*(_reach(adj, identifier, OWNERS) for identifier in identifiers)))
    publications = {n for key in owners | identifiers for n in adj[key] if _kind(n) == "ad"}
    return owners | identifiers | publications


def _developers_phrase(count: int) -> str:
    """The form of "застройщик" after "у N": 1 застройщика, 2 застройщиков, 21 застройщика."""
    return "застройщика" if count % 10 == 1 and count % 100 != 11 else "застройщиков"


def _findings(graph: _Graph, keep: set[str]) -> list[GraphFinding]:
    """Phones and accounts that tie together two or more developers, directly or through publications."""
    findings: list[GraphFinding] = []
    for key in keep:
        node = graph.nodes[key]
        # A saved search of an aggregator collects the offers of everyone: it is not somebody's account.
        if node.type not in IDENTIFIERS or node.platform is Platform.aggregator:
            continue
        owners = _reach(graph.adj, key, OWNERS) & keep
        direct = {owner for owner in owners if _kind(owner) == "developer"}
        developers = direct | {
            n
            for owner in owners
            if _kind(owner) == "object"
            for n in graph.adj[owner]
            if n in keep and _kind(n) == "developer"
        }
        if len(developers) < 2:
            continue
        objects = {owner for owner in owners if _kind(owner) == "object"} | {
            n for developer in direct for n in graph.adj[developer] if n in keep and _kind(n) == "object"
        }
        subject = "телефон" if node.type == "phone" else "аккаунт"
        findings.append(
            GraphFinding(
                kind="shared_phone" if node.type == "phone" else "shared_account",
                value=key.partition(":")[2],
                label=f"Один {subject} у {len(developers)} {_developers_phrase(len(developers))}",
                developer_ids=sorted(int(n.partition(":")[2]) for n in developers),
                object_ids=sorted(int(n.partition(":")[2]) for n in objects),
            )
        )
    return sorted(findings, key=lambda f: (-len(f.developer_ids), f.kind, f.value))


def _truncate(graph: _Graph, candidates: set[str], seeds: list[str], findings: list[GraphFinding]) -> set[str]:
    """`MAX_NODES` nodes of the candidates, taken by a best-first walk so that what is kept stays connected.

    The walk starts at the seeds, then at the nodes of findings, then at the best connected of the rest.
    """

    def rank(key: str) -> tuple[int, int, str]:
        return _TIER[_kind(key)], -len(graph.adj[key] & candidates), key

    flagged = {
        key
        for finding in findings
        for key in (
            f"{'phone' if finding.kind == 'shared_phone' else 'account'}:{finding.value}",
            *(f"developer:{developer_id}" for developer_id in finding.developer_ids),
            *(f"object:{object_id}" for object_id in finding.object_ids),
        )
    }
    kept: set[str] = set()
    for root in [*seeds, *sorted(flagged & candidates, key=rank), *sorted(candidates, key=rank)]:
        if root in kept:
            continue
        frontier = [(rank(root), root)]
        while frontier and len(kept) < MAX_NODES:
            _, key = heapq.heappop(frontier)
            if key in kept:
                continue
            kept.add(key)
            for neighbour in graph.adj[key] & candidates:
                if neighbour not in kept:
                    heapq.heappush(frontier, (rank(neighbour), neighbour))
        if len(kept) >= MAX_NODES:
            break
    return kept


def build_graph(
    session: Session, scope: TerritoryScope, *, object_id: int | None = None, developer_id: int | None = None
) -> Graph:
    """The graph of the whole scope, or the two-hop neighbourhood of one object or developer."""
    graph = _load(session, scope)
    seeds = [f"object:{object_id}"] if object_id is not None else []
    if developer_id is not None:
        seeds = [f"developer:{developer_id}"]
    if seeds:
        candidates = _neighbourhood(graph.adj, set(seeds))
    else:
        candidates = {key for key, neighbours in graph.adj.items() if neighbours}  # a node alone shows no link

    findings = _findings(graph, candidates)
    truncated = len(candidates) > MAX_NODES
    kept = candidates
    if truncated:
        kept = _truncate(graph, candidates, seeds, findings)
        findings = _findings(graph, kept)
    return Graph(
        nodes=[graph.nodes[key] for key in sorted(kept)],
        edges=[
            GraphEdge(source=source, target=target, type=kind)
            for source, target, kind in sorted(graph.edges)
            if source in kept and target in kept
        ],
        findings=findings,
        truncated=truncated,
    )
