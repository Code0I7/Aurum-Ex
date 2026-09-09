import { useMemo } from "react";
import { Combobox } from "@/components/ui/Combobox";
import { getCategoryIcon } from "@/lib/icons";
import { buildHierarchicalCategories, categoryPath, translateCategoryName } from "@/lib/categoryLabels";
import { useTranslation } from "@/lib/i18n";

/**
 * Единственное место, где в приложении выбирают категорию.
 *
 * Раньше в каждом экране стоял свой `<select>`: в операции, в фильтре
 * списка, в отчётах, в наблюдении за товарами. Списки были одинаковыми, а
 * поведение — нет, и добавить поиск сразу везде было некуда. Теперь
 * поведение живёт здесь, а экраны передают только набор категорий.
 *
 * Поиск идёт по полному пути, а не по имени листа: «прод сыр» находит
 * «Продукты · Молочное · Сыр». В обычном списке показано короткое имя с
 * отступом — путь целиком в каждой строке был бы нечитаем, — а при поиске
 * наоборот полный путь: найденный «Сыр» без родителя не отвечает, тот ли
 * это сыр.
 *
 * Два исключения, и оба про одно и то же — риск выбрать не ту категорию:
 *
 *  * **в закрытом поле всегда полный путь.** «Зарплата» у Ивана и
 *    «Зарплата» у Ольги — разные категории с одинаковым именем, и поле,
 *    показывающее только лист, не даёт проверить, что выбрано;
 *  * **одинаковые имена в списке тоже разворачиваются в путь.** Отступ
 *    показывает вложенность, но не родителя: две «Зарплаты» на одной
 *    глубине выглядят одинаково, а их родители могут быть за экраном.
 *    Уникальные имена при этом остаются короткими — разворачивать их
 *    значило бы засорять список ради случая, которого нет.
 */

export interface PickableCategory {
  id: number;
  name: string;
  parent_id: number | null;
  icon?: string | null;
  color?: string | null;
  /** Заголовок раздела: «Расходы» / «Доходы» в фильтрах, где в одном
   *  списке лежат категории обоих видов. */
  group?: string;
}

interface CategoryPickerProps {
  id?: string;
  /** Категории, из которых можно выбирать — уже отфильтрованные по виду. */
  categories: PickableCategory[];
  /** Идентификатор строкой — как хранится в состоянии формы. */
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  /** Подпись пустого пункта («Все категории», «Без категории»). Не задана —
   *  пустой выбор недоступен. */
  emptyLabel?: string;
  disabled?: boolean;
  className?: string;
}

export function CategoryPicker({
  id,
  categories,
  value,
  onChange,
  placeholder,
  emptyLabel,
  disabled,
  className,
}: CategoryPickerProps) {
  const { language } = useTranslation();

  const options = useMemo(() => {
    const ordered = buildHierarchicalCategories(categories, language);
    // Имена, встречающиеся больше одного раза: только их и нужно
    // разворачивать в полный путь.
    const seen = new Map<string, number>();
    for (const category of ordered) {
      const name = translateCategoryName(category.name);
      seen.set(name, (seen.get(name) ?? 0) + 1);
    }
    return ordered.map((category) => {
        const Icon = getCategoryIcon(category.icon);
        const name = translateCategoryName(category.name);
        const path = categoryPath(category, categories);
        return {
          value: String(category.id),
          label: (seen.get(name) ?? 0) > 1 ? path : name,
          // Полный путь для закрытого поля и для поиска — там короткого
          // имени всегда мало.
          search: path,
          depth: category.depth,
          group: category.group,
          icon: (
            <Icon
              size={14}
              className="shrink-0"
              // Цвет категории — её опознавательный знак в отчётах и на
              // круге. В списке он же помогает найти нужную строку быстрее,
              // чем чтение названий подряд.
              style={category.color ? { color: category.color } : undefined}
            />
          ),
      };
    });
  }, [categories, language]);

  return (
    <Combobox
      id={id}
      options={options}
      value={value}
      onChange={onChange}
      placeholder={placeholder}
      emptyLabel={emptyLabel}
      disabled={disabled}
      className={className}
      // В закрытом поле — полный путь. Именно там ошибка и не видна:
      // выбрал «Зарплату» Ольги, а в поле написано просто «Зарплата».
      selectedLabel="search"
    />
  );
}
