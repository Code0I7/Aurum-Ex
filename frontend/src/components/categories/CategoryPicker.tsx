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

  const options = useMemo(
    () =>
      buildHierarchicalCategories(categories, language).map((category) => {
        const Icon = getCategoryIcon(category.icon);
        return {
          value: String(category.id),
          label: translateCategoryName(category.name),
          search: categoryPath(category, categories),
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
      }),
    [categories, language]
  );

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
    />
  );
}
