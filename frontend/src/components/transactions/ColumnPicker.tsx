import { useState } from "react";
import { ChevronDown, ChevronUp, Columns3, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { useTranslation } from "@/lib/i18n";
import { COLUMNS, DEFAULT_LAYOUT, type ColumnId, type ColumnLayout } from "@/components/transactions/columns";

interface ColumnPickerProps {
  layout: ColumnLayout;
  onChange: (layout: ColumnLayout) => void;
}

/**
 * Настройка колонок: что показывать и в каком порядке.
 *
 * Порядок меняется кнопками, а не перетаскиванием. Перетаскивание внутри
 * модального окна на телефоне спорит с прокруткой самого окна, а кнопки
 * работают одинаково мышью, пальцем и с клавиатуры — здесь это важнее
 * плавности, потому что настройку открывают раз в месяц.
 *
 * Обязательные колонки показаны, но их галочка заблокирована: строка без
 * даты и суммы не читается, и запрещать это лучше видимо, чем молча
 * возвращать колонку обратно.
 */
export function ColumnPicker({ layout, onChange }: ColumnPickerProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  const toggle = (id: ColumnId) => {
    const visible = layout.visible.includes(id)
      ? layout.visible.filter((current) => current !== id)
      : [...layout.visible, id];
    // Порядок задаёт layout.order, а не последовательность включения:
    // возвращённая колонка встаёт на своё прежнее место, а не в конец.
    onChange({ ...layout, visible: layout.order.filter((current) => visible.includes(current)) });
  };

  const move = (id: ColumnId, direction: -1 | 1) => {
    const order = [...layout.order];
    const index = order.indexOf(id);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= order.length) return;
    [order[index], order[target]] = [order[target], order[index]];
    onChange({ order, visible: order.filter((current) => layout.visible.includes(current)) });
  };

  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)} className="gap-1.5">
        <Columns3 size={15} />
        <span className="hidden sm:inline">{t("transactions.columns")}</span>
      </Button>

      <Dialog open={open} onClose={() => setOpen(false)} title={t("transactions.columns")}>
        <ul className="flex flex-col divide-y divide-gridline">
          {layout.order.map((id) => {
            const column = COLUMNS.find((item) => item.id === id);
            if (!column) return null;
            const checked = layout.visible.includes(id);

            return (
              <li key={id} className="flex items-center gap-3 py-2">
                <label className="flex min-w-0 flex-1 items-center gap-2.5 text-sm text-text-primary">
                  <input
                    type="checkbox"
                    checked={checked}
                    disabled={column.required}
                    onChange={() => toggle(id)}
                    className="h-4 w-4 shrink-0 accent-text-primary disabled:opacity-40"
                  />
                  <span className="truncate">{t(column.labelKey)}</span>
                  {column.required && <span className="shrink-0 text-xs text-text-muted">{t("transactions.columnRequired")}</span>}
                </label>

                <span className="flex shrink-0 items-center gap-0.5">
                  <button
                    type="button"
                    onClick={() => move(id, -1)}
                    title={t("transactions.columnUp")}
                    className="rounded p-1 text-text-muted hover:bg-surface-2 hover:text-text-primary"
                  >
                    <ChevronUp size={15} />
                  </button>
                  <button
                    type="button"
                    onClick={() => move(id, 1)}
                    title={t("transactions.columnDown")}
                    className="rounded p-1 text-text-muted hover:bg-surface-2 hover:text-text-primary"
                  >
                    <ChevronDown size={15} />
                  </button>
                </span>
              </li>
            );
          })}
        </ul>

        <div className="mt-4 flex justify-between gap-2">
          <Button variant="ghost" onClick={() => onChange(DEFAULT_LAYOUT)} className="gap-1.5">
            <RotateCcw size={14} />
            {t("transactions.columnsReset")}
          </Button>
          <Button onClick={() => setOpen(false)}>{t("common.done")}</Button>
        </div>
      </Dialog>
    </>
  );
}
