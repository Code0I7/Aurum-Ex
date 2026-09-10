from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import CategoryKind


class CategoryBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    kind: CategoryKind
    icon: str | None = None
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    sort_order: int = 0
    # Родитель. Глубина произвольная: одноуровневое ограничение снято, и
    # routes/categories.py проверяет только циклы, совпадение вида и предел
    # MAX_DEPTH.
    parent_id: int | None = None
    # Держать категорию на виду в списке наблюдения на вкладке планирования.
    is_watched: bool = False


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    icon: str | None = None
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    sort_order: int | None = None
    # The route uses exclude_unset=True, so sending parent_id explicitly as
    # null (as opposed to omitting the field) is what turns a subcategory
    # back into a top-level category.
    parent_id: int | None = None
    # Включить или убрать из списка наблюдения. Отдельным полем, а не
    # вместе с прочей правкой: переключается щелчком из таблицы наблюдения,
    # где ничего другого не меняется.
    is_watched: bool | None = None
    # Применить цвет и значок ко всей ветке под этой категорией. Только в
    # правке и отдельным флагом, а не автоматически: подкатегория могла быть
    # покрашена нарочно, и перекрасить её без спроса значило бы стереть
    # решение человека. Полем CategoryBase быть не может — оно попало бы в
    # конструктор модели при создании.
    apply_style_to_children: bool = False


class CategoryRead(CategoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_default: bool


class CategoryUsage(BaseModel):
    """Что зацепит удаление категории — считается перед показом вопроса.

    Не поле CategoryRead: считать это для каждой из полутора сотен категорий
    на каждой загрузке списка незачем, а спрашивают об этом раз в жизни
    категории — ровно перед удалением.
    """

    # Операций, которые ссылаются на категорию: строкой или своим сплитом.
    # Считаются разные операции, а не ссылки: сплит-операция с двумя
    # строками одной категории — это одна операция, а не две.
    transactions: int
    # Позиций чека с этой категорией. Отдельно от операций: позиция теряет
    # категорию так же молча, но операция при этом остаётся при своей.
    items: int
    # Прямых подкатегорий. Они НЕ удаляются вместе с родителем: внешний ключ
    # parent_id стоит ON DELETE SET NULL, поэтому дети всплывают в корень
    # отдельными ветками верхнего уровня. Об этом обязательно предупредить —
    # само по себе это выглядит как «дерево рассыпалось».
    children: int
    # Вся ветка ниже, включая внуков. Показывает настоящий масштаб, когда
    # детей двое, а под ними ещё двадцать.
    descendants: int
    # Операции в этой ветке ниже. Они удаление переживут без потерь —
    # категория у них своя, — но человеку важно видеть, что за строкой
    # «1 операция» стоит ветка на сотню.
    descendant_transactions: int
