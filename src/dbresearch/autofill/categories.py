"""Map checked boxes and header text to ADMIN categories (never creates categories)."""

import re
import uuid
from dataclasses import dataclass

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from dbresearch.models import Category, CategoryGroup

GROUP_MIN = 80
OPTION_MIN = 70
OPTION_MARGIN = 10


def compact(text: str) -> str:
    return re.sub(r"\s+", "", re.sub(r"\(.*?\)", "", text))


@dataclass(frozen=True)
class Option:
    id: uuid.UUID
    name: str
    names: tuple[str, ...]  # name + aliases, compacted


@dataclass(frozen=True)
class Group:
    id: uuid.UUID
    key: str
    name: str
    multi: bool
    names: tuple[str, ...]
    options: tuple[Option, ...]


@dataclass(frozen=True)
class Match:
    group_key: str
    category_id: uuid.UUID
    category_name: str
    score: float


class CategoryIndex:
    def __init__(self, groups: list[Group]) -> None:
        self.groups = {g.key: g for g in groups}

    @classmethod
    def load(cls, db: Session) -> "CategoryIndex":
        groups = []
        for group in db.scalars(select(CategoryGroup).order_by(CategoryGroup.sort)):
            options = db.scalars(
                select(Category)
                .where(Category.group_id == group.id, Category.active.is_(True))
                .order_by(Category.sort)
            )
            groups.append(
                Group(
                    group.id,
                    group.key,
                    group.name_th,
                    group.multi,
                    tuple(compact(n) for n in [group.name_th, *group.aliases]),
                    tuple(
                        Option(o.id, o.name_th, tuple(compact(n) for n in [o.name_th, *o.aliases]))
                        for o in options
                    ),
                )
            )
        return cls(groups)

    def match_group(self, heading: str) -> Group | None:
        text = compact(heading)
        best: tuple[float, Group | None] = (0.0, None)
        for group in self.groups.values():
            for name in group.names:
                score = fuzz.ratio(name, text[: len(name) + 2])
                if score > best[0]:
                    best = (score, group)
        return best[1] if best[0] >= GROUP_MIN else None

    def match_option(self, group: Group, label: str) -> Match | None:
        """Best option in the group, only if clearly better than the next-best option."""
        text = compact(label)
        if not text:
            return None
        scored = sorted(
            ((max(fuzz.ratio(n, text) for n in o.names), o) for o in group.options),
            key=lambda pair: pair[0],
            reverse=True,
        )
        if not scored:
            return None
        best, option = scored[0]
        runner = scored[1][0] if len(scored) > 1 else 0.0
        if best >= OPTION_MIN and best - runner >= OPTION_MARGIN:
            return Match(group.key, option.id, option.name, round(best, 1))
        return None

    def find_in_text(self, group_key: str, text: str, minimum: float = 92) -> Match | None:
        """Look for any option name/alias of a group inside running text (e.g. the agency)."""
        group = self.groups.get(group_key)
        if group is None:
            return None
        haystack = compact(text)
        best: tuple[float, Option | None] = (0.0, None)
        for option in group.options:
            for name in option.names:
                if len(name) < 3:
                    continue
                score = 100.0 if name in haystack else fuzz.partial_ratio(name, haystack)
                if score > best[0]:
                    best = (score, option)
        if best[1] is None or best[0] < minimum:
            return None
        return Match(group_key, best[1].id, best[1].name, round(best[0], 1))
