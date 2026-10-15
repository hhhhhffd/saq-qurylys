from dataclasses import dataclass

from sqlalchemy import Select, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.models import AppUser, Territory


@dataclass(frozen=True)
class TerritoryScope:
    """Territories visible to a user: their own territory and all descendants. `ids=None` = everything."""

    ids: frozenset[int] | None

    @property
    def is_unrestricted(self) -> bool:
        return self.ids is None

    def contains(self, territory_id: int | None) -> bool:
        if self.ids is None:
            return True
        return territory_id is not None and territory_id in self.ids

    def restrict[*Ts](
        self, stmt: Select[*Ts], column: InstrumentedAttribute[int] | InstrumentedAttribute[int | None]
    ) -> Select[*Ts]:
        if self.ids is None:
            return stmt
        return stmt.where(column.in_(self.ids))


def build_scope(session: Session, user: AppUser) -> TerritoryScope:
    if user.territory_id is None:
        return TerritoryScope(ids=None)
    tree = select(Territory.id).where(Territory.id == user.territory_id).cte("tree", recursive=True)
    tree = tree.union_all(select(Territory.id).join(tree, Territory.parent_id == tree.c.id))
    return TerritoryScope(ids=frozenset(session.scalars(select(tree.c.id))))
