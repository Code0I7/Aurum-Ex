import { useEffect, useRef, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { HelpBadge } from "@/components/ui/HelpBadge";
import { Input, Label } from "@/components/ui/Input";
import { Combobox } from "@/components/ui/Combobox";
import { suggestProducts } from "@/api/products";
import { useCreateProduct, useUnits } from "@/hooks/useProducts";
import { useTranslation } from "@/lib/i18n";
import { formatCurrency } from "@/lib/format";
import type { Product, TransactionItemInput, Unit } from "@/types";

interface ItemsEditorProps {
  items: TransactionItemInput[];
  onChange: (items: TransactionItemInput[]) => void;
  /** Сумма операции — чтобы показать нераспределённый остаток. */
  total: string;
}

/**
 * Состав чека.
 *
 * Позиции намеренно не обязаны сходиться с суммой операции. Помнить, что
 * купили хлеб и молоко, не помня цен, — обычное дело, и отказ такое хранить
 * потерял бы память целиком. Остаток показывается, а не подгоняется: сумма
 * операции остаётся источником истины.
 *
 * Чек без позиций тоже нормален. Редактор свёрнут по умолчанию, чтобы
 * быстрый ввод оставался одним действием.
 */
/** Имя базовой меры для вида выбранной единицы: «л» для миллилитров,
 *  «кг» для граммов. Пусто, когда единица не выбрана или базовой у её
 *  вида нет. */
function baseUnitName(units: Unit[] | undefined, unitId: number | null | undefined): string | null {
  if (!units || !unitId) return null;
  const unit = units.find((item) => item.id === unitId);
  if (!unit) return null;
  const base = units.find((item) => item.kind === unit.kind && item.is_base);
  return base ? `₽ / ${base.name}` : null;
}

export function ItemsEditor({ items, onChange, total }: ItemsEditorProps) {
  const { t } = useTranslation();
  const { data: units } = useUnits();

  const allocated = items.reduce((sum, item) => sum + Number(item.amount ?? 0), 0);
  const remainder = Number(total || 0) - allocated;

  function update(index: number, patch: Partial<TransactionItemInput>) {
    const next = items.map((item, position) => (position === index ? { ...item, ...patch } : item));
    // Сумма позиции считается сама, когда известны цена и количество:
    // заставлять человека перемножать два числа, которые он только что
    // ввёл, незачем. Введённую вручную сумму не трогаем.
    const item = next[index];
    // Цена считается за БАЗОВУЮ меру — за литр, за килограмм, — а не за
    // введённую единицу. Пол-литра воды за 36,99 давали «0,074 за
    // миллилитр»: число верное и бесполезное, и человек решал, что
    // бутылку воды в чек просто не занести. Теперь там 73,98 за литр —
    // ровно то, что написано на ценнике.
    //
    // Отсюда коэффициент в обеих формулах: сумма = количество × коэффициент
    // × цена. Для 500 мл по 73,98 это 500 × 0,001 × 73,98 = 36,99.
    const factor = Number(units?.find((unit) => unit.id === item.unit_id)?.factor ?? 1) || 1;
    if (("price" in patch || "quantity" in patch || "unit_id" in patch) && item.price && item.quantity) {
      item.amount = (Number(item.price) * Number(item.quantity) * factor).toFixed(2);
    } else if ("amount" in patch && item.amount && item.quantity && Number(item.quantity) !== 0) {
      // Вписали сумму — цена за базовую меру выводится из неё.
      item.price = (Number(item.amount) / (Number(item.quantity) * factor)).toFixed(4);
    }
    onChange(next);
  }

  function addRow() {
    onChange([...items, { name: "", quantity: null, price: null, amount: null }]);
  }

  function removeRow(index: number) {
    onChange(items.filter((_, position) => position !== index));
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1.5">
          <Label>{t("items.title")}</Label>
          <HelpBadge hintKey="items.priceHint" />
        </span>
        <button
          type="button"
          onClick={addRow}
          className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-text-muted hover:bg-surface-2 hover:text-text-primary"
        >
          <Plus size={14} />
          {t("items.add")}
        </button>
      </div>

      {items.length === 0 ? (
        <p className="text-xs text-text-muted">{t("items.emptyHint")}</p>
      ) : (
        <ul className="space-y-2">
          {items.map((item, index) => (
            <li key={index} className="rounded-lg border border-border p-2.5">
              <div className="flex items-start gap-2">
                <div className="min-w-0 flex-1">
                  <ProductNameField
                    value={item.name}
                    onChange={(name) => update(index, { name, product_id: null })}
                    onPick={(product) =>
                      update(index, {
                        name: product.name,
                        product_id: product.id,
                        // Количество и единица прошлой покупки. Хлеб берут по
                        // одной штуке, молоко по литру — вводить одно и то же
                        // в каждом чеке незачем.
                        //
                        // Единица последней покупки важнее записанной в
                        // справочнике: чек заполняют по чеку, а в справочнике
                        // лежит обычная мера товара. Если покупок ещё не
                        // было, берётся справочник.
                        quantity: product.last_quantity ?? null,
                        unit_id: product.last_unit_id ?? product.unit_id,
                      })
                    }
                  />
                </div>
                <button
                  type="button"
                  onClick={() => removeRow(index)}
                  aria-label={t("common.delete")}
                  className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-danger"
                >
                  <Trash2 size={14} />
                </button>
              </div>

              {/* Две строки по паре полей, а не четыре в ряд. Четыре поля
                  в одной строке жались даже на широком экране, а порядок
                  повторяет то, как человек читает ценник: сколько взял —
                  сколько отдал. Цена за меру стоит последней, потому что
                  её обычно не вводят, а получают. */}
              <div className="mt-2 grid grid-cols-2 gap-2">
                <Input
                  type="number"
                  // step="any", а не «сотые»: 260 г за 64,99 дают 249,9615
                  // за килограмм, и браузер с шагом в копейку отказывался
                  // принимать такое число молча — поле просто не
                  // отправлялось.
                  step="any"
                  min="0"
                  placeholder={t("items.quantity")}
                  value={item.quantity ?? ""}
                  onChange={(event) => update(index, { quantity: event.target.value || null })}
                />
                <Combobox
                  options={(units ?? []).map((unit) => ({ value: String(unit.id), label: unit.name }))}
                  value={item.unit_id ? String(item.unit_id) : ""}
                  onChange={(value) => update(index, { unit_id: value ? Number(value) : null })}
                  placeholder={t("items.unit")}
                  emptyLabel={t("items.unit")}
                />
              </div>

              <div className="mt-2 grid grid-cols-2 gap-2">
                <Input
                  type="number"
                  step="0.01"
                  min="0"
                  placeholder={t("items.amount")}
                  value={item.amount ?? ""}
                  onChange={(event) => update(index, { amount: event.target.value || null })}
                />
                <Input
                  type="number"
                  step="any"
                  min="0"
                  placeholder={
                    // Подпись называет базовую меру: «₽ / л» вместо
                    // безликого «Цена за ед.», за которым приходилось
                    // догадываться, за что именно.
                    baseUnitName(units, item.unit_id) ?? t("items.price")
                  }
                  value={item.price ?? ""}
                  onChange={(event) => update(index, { price: event.target.value || null })}
                />
              </div>

              <CreateProductButton
                name={item.name}
                unitId={item.unit_id ?? null}
                quantity={item.quantity ?? null}
                bound={item.product_id != null}
                onCreated={(product) => update(index, { name: product.name, product_id: product.id })}
              />
            </li>
          ))}
        </ul>
      )}

      {/* Остаток. Показывается только когда позиции есть и они не покрывают
          сумму целиком — иначе строка была бы шумом на каждом чеке. */}
      {items.length > 0 && Math.abs(remainder) >= 0.01 && (
        <p className="text-xs text-text-muted">
          {remainder > 0
            ? t("items.remainder", { amount: formatCurrency(remainder) })
            : t("items.overAllocated", { amount: formatCurrency(Math.abs(remainder)) })}
        </p>
      )}
    </div>
  );
}

/**
 * Поле названия с подсказкой из справочника товаров.
 *
 * Только подсказки. Заведение товара живёт отдельной кнопкой ниже и
 * появляется, когда указаны количество и единица: раньше «создать» висело
 * прямо в этом списке и срабатывало на полуслове, ещё до того, как
 * человек выбрал меру. Товар попадал в справочник без единицы, а без неё
 * кривая цены не строится — то есть ровно то, ради чего справочник и
 * заведён, не работало.
 */
function ProductNameField({
  value,
  onChange,
  onPick,
}: {
  value: string;
  onChange: (value: string) => void;
  onPick: (product: Product) => void;
}) {
  const { t } = useTranslation();
  const [suggestions, setSuggestions] = useState<Product[]>([]);
  const [open, setOpen] = useState(false);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    if (value.trim().length < 2) {
      setSuggestions([]);
      return;
    }
    // Задержка: подсказка на каждое нажатие клавиши — это запрос на букву,
    // а список товаров меняется куда медленнее, чем человек печатает.
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      suggestProducts(value)
        .then(setSuggestions)
        .catch(() => setSuggestions([]));
    }, 250);
    return () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
    };
  }, [value]);

  return (
    <div className="relative">
      <Input
        placeholder={t("items.namePlaceholder")}
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        // Закрытие с задержкой: без неё клик по подсказке не успевает
        // сработать — blur снимает список раньше.
        onBlur={() => window.setTimeout(() => setOpen(false), 150)}
      />
      {open && suggestions.length > 0 && (
        <ul className="absolute z-20 mt-1 max-h-48 w-full overflow-y-auto rounded-md border border-border bg-surface-1 shadow-md">
          {suggestions.map((product) => (
            <li key={product.id}>
              <button
                type="button"
                onClick={() => {
                  onPick(product);
                  setOpen(false);
                }}
                className="flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-sm hover:bg-surface-2"
              >
                <span className="truncate">{product.name}</span>
                {product.unit_name && (
                  <span className="shrink-0 text-xs text-text-muted">{product.unit_name}</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * «Завести товар» — отдельной строкой под полями позиции.
 *
 * Появляется, когда набрано название, указаны количество и единица, и
 * товар с таким именем ещё не заведён. Порядок не случайный: в справочник
 * уезжает единица измерения, и предлагать заведение раньше, чем она
 * выбрана, значит заводить товар, по которому не построится кривая цены.
 *
 * Регулярные покупки почти всегда впервые вписываются здесь, в чеке, а не
 * в справочнике: уходить за этим на другую страницу посреди ввода операции
 * никто не станет, и товар просто не заводится никогда.
 */
function CreateProductButton({
  name,
  unitId,
  quantity,
  bound,
  onCreated,
}: {
  name: string;
  unitId: number | null;
  quantity: string | null;
  /** Позиция уже привязана к товару — заводить нечего. */
  bound: boolean;
  onCreated: (product: Product) => void;
}) {
  const { t } = useTranslation();
  const createProduct = useCreateProduct();
  const [known, setKnown] = useState<boolean | null>(null);
  const trimmed = name.trim();
  const ready = !bound && trimmed.length >= 2 && unitId !== null && Boolean(quantity);

  useEffect(() => {
    if (!ready) {
      setKnown(null);
      return;
    }
    let cancelled = false;
    // Товар с таким именем мог быть заведён раньше — тогда кнопки быть не
    // должно вовсе. Проверка по точному совпадению, как и склейка позиции
    // с товаром на сервере.
    suggestProducts(trimmed)
      .then((found) => {
        if (!cancelled) {
          setKnown(found.some((product) => product.name.toLowerCase() === trimmed.toLowerCase()));
        }
      })
      .catch(() => {
        if (!cancelled) setKnown(false);
      });
    return () => {
      cancelled = true;
    };
  }, [ready, trimmed]);

  if (!ready || known !== false) return null;

  return (
    <button
      type="button"
      disabled={createProduct.isPending}
      onClick={async () => {
        const product = await createProduct.mutateAsync({
          name: trimmed,
          unit_id: unitId,
          barcode: null,
          notes: null,
        });
        onCreated(product);
      }}
      className="mt-2 flex items-center gap-1.5 text-xs text-series-1 hover:underline disabled:opacity-50"
    >
      <Plus size={13} className="shrink-0" />
      <span className="truncate">{t("items.createProduct", { name: trimmed })}</span>
    </button>
  );
}
