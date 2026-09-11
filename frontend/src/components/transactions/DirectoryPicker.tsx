import { useState } from "react";
import { Check, Plus, X } from "lucide-react";
import { Input } from "@/components/ui/Input";
import { Combobox } from "@/components/ui/Combobox";
import { useTranslation } from "@/lib/i18n";

interface DirectoryPickerProps {
  id: string;
  /** Уже заведённые записи справочника. */
  options: Array<{ id: number; name: string }>;
  /** Идентификатор строкой — как хранится в состоянии формы. */
  value: string;
  onChange: (value: string) => void;
  /** Подпись пустого выбора. Отсутствует — выбор обязателен. */
  emptyLabel?: string;
  placeholder: string;
  /** Заводит новую запись и возвращает её идентификатор. */
  onCreate: (name: string) => Promise<number>;
  disabled?: boolean;
}

/**
 * Выбор из справочника с возможностью тут же завести новую запись.
 *
 * Так и было задумано с самого начала — в hooks/useDirectories.ts это
 * записано словами: «набрал новое имя — оно завелось». Не было только
 * самого поля: списки заполнялись переносом таблицы, а через приложение
 * ни человека, ни магазин, ни контрагента завести было нельзя вообще.
 * Подсказка под пустым списком при этом отправляла в справочник, которого
 * в интерфейсе нет.
 *
 * Заводить прямо здесь, а не на отдельной странице справочников: ходить за
 * этим в другой раздел значит прерывать ввод операции ради заведения
 * магазина — и в итоге поле просто перестают заполнять.
 */
export function DirectoryPicker({
  id,
  options,
  value,
  onChange,
  emptyLabel,
  placeholder,
  onCreate,
  disabled,
}: DirectoryPickerProps) {
  const { t } = useTranslation();
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  async function commit() {
    const trimmed = name.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    try {
      const createdId = await onCreate(trimmed);
      onChange(String(createdId));
      setAdding(false);
      setName("");
    } finally {
      setBusy(false);
    }
  }

  if (adding) {
    return (
      <div className="flex gap-1.5">
        <Input
          id={id}
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder={placeholder}
          autoFocus
          // Enter подтверждает, Escape отменяет. Обычной кнопки submit
          // здесь быть не может: поле стоит внутри формы операции, и
          // нажатие Enter отправило бы всю форму вместо создания записи.
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              void commit();
            }
            if (event.key === "Escape") {
              event.preventDefault();
              setAdding(false);
              setName("");
            }
          }}
        />
        <button
          type="button"
          onClick={() => void commit()}
          disabled={busy || name.trim() === ""}
          aria-label={t("common.save")}
          className="shrink-0 rounded-lg border border-border px-2 text-text-muted hover:bg-surface-2 hover:text-text-primary disabled:opacity-40"
        >
          <Check size={15} />
        </button>
        <button
          type="button"
          onClick={() => {
            setAdding(false);
            setName("");
          }}
          aria-label={t("common.cancel")}
          className="shrink-0 rounded-lg border border-border px-2 text-text-muted hover:bg-surface-2 hover:text-text-primary"
        >
          <X size={15} />
        </button>
      </div>
    );
  }

  return (
    <div className="flex gap-1.5">
      {/* Свой список, а не браузерный: нативный рисуется средствами
          системы, и как он выглядит на конкретной связке «браузер плюс
          телефон», не знает никто. Заодно появляется поиск, без которого
          полтора десятка людей или магазинов уже листаются. */}
      <Combobox
        id={id}
        className="min-w-0 flex-1"
        options={options.map((option) => ({ value: String(option.id), label: option.name }))}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        emptyLabel={emptyLabel}
        disabled={disabled}
      />
      <button
        type="button"
        onClick={() => setAdding(true)}
        aria-label={t("common.add")}
        title={t("common.add")}
        className="shrink-0 rounded-lg border border-border px-2 text-text-muted hover:bg-surface-2 hover:text-text-primary"
      >
        <Plus size={15} />
      </button>
    </div>
  );
}
