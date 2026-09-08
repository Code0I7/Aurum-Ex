"""Дерево категорий произвольной глубины.

Раньше вложенность была одноуровневой, и «верхняя категория» вычислялась
одним выражением — `coalesce(parent_id, id)`. С произвольной глубиной этого
мало: у «Продукты → Молочное → Сыр» родитель не корень, и подъём на один шаг
относил бы сыр к молочному, а не к продуктам.

Здесь одно место, которое умеет ходить по дереву, — чтобы каждый отчёт не
решал этот вопрос заново и не решал по-своему.

Глубина ограничена (MAX_DEPTH): не из-за запросов, а ради читаемости.
Категория на седьмом уровне не помещается ни в один список, а найти её в
выпадающем меню невозможно. Ограничение щедрое — в настоящих таблицах
встречаются два уровня, изредка три.
"""
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category

# Сколько уровней разрешено. Корень — уровень 1, поэтому 5 означает
# «Продукты → Молочное → Сыр → Твёрдый → Пармезан».
MAX_DEPTH = 5


@dataclass
class CategoryTree:
    """Разобранное дерево: кто чей родитель и кто чьи дети.

    Строится один раз на запрос и передаётся по функциям. Ходить в базу за
    каждым родителем нельзя: в отчёте за год таких обращений были бы
    тысячи.
    """

    parents: dict[int, int | None]
    children: dict[int, list[int]]

    def top_level_of(self, category_id: int) -> int:
        """Корень ветки, в которой лежит категория.

        Цикл в данных не должен вешать отчёт: если он всё-таки возник (ручная
        правка базы, сломанный импорт), подъём останавливается и возвращает
        последнюю категорию, а не крутится вечно.
        """
        seen: set[int] = set()
        current = category_id
        while True:
            parent = self.parents.get(current)
            if parent is None or parent in seen:
                return current
            seen.add(current)
            current = parent

    def ancestors_of(self, category_id: int) -> list[int]:
        """Все предки снизу вверх, не включая саму категорию."""
        result: list[int] = []
        seen: set[int] = set()
        current = self.parents.get(category_id)
        while current is not None and current not in seen:
            result.append(current)
            seen.add(current)
            current = self.parents.get(current)
        return result

    def descendants_of(self, category_id: int) -> list[int]:
        """Вся ветка вниз, не включая саму категорию.

        Нужна там, где план или бюджет стоит на ветке, а тратят по листьям:
        сравнивать ветку только с тем, что записано прямо в неё, значило бы
        показать нулевой факт при полном холодильнике.
        """
        result: list[int] = []
        queue = list(self.children.get(category_id, []))
        seen: set[int] = set()
        while queue:
            current = queue.pop()
            if current in seen:
                continue
            seen.add(current)
            result.append(current)
            queue.extend(self.children.get(current, []))
        return result

    def subtree_of(self, category_id: int) -> list[int]:
        """Категория вместе со всей веткой под ней."""
        return [category_id, *self.descendants_of(category_id)]

    def depth_of(self, category_id: int) -> int:
        """Уровень категории: корень — 1."""
        return len(self.ancestors_of(category_id)) + 1

    def depth_below(self, category_id: int) -> int:
        """Насколько глубока ветка под категорией. 1 — детей нет.

        Нужна при перемещении: ветку из трёх уровней нельзя подвесить так,
        чтобы её низ вышел за предел.
        """
        best = 1
        for child in self.children.get(category_id, []):
            best = max(best, 1 + self.depth_below(child))
        return best


async def load_category_tree(session: AsyncSession) -> CategoryTree:
    rows = (await session.execute(select(Category.id, Category.parent_id))).all()
    parents = {category_id: parent_id for category_id, parent_id in rows}
    children: dict[int, list[int]] = defaultdict(list)
    for category_id, parent_id in rows:
        if parent_id is not None:
            children[parent_id].append(category_id)
    return CategoryTree(parents=parents, children=dict(children))
