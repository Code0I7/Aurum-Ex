import { useEffect, useRef, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { HelpBadge } from "@/components/ui/HelpBadge";
import { useConfirm } from "@/components/ui/ConfirmProvider";
import { Input, Label } from "@/components/ui/Input";
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
  /**
   * Категория самой операции, если она одна. Нужна только товару,
   * заводимому прямо отсюда: у позиции своей категории обычно нет — она
   * и так берётся у операции, — а в справочнике из-за этого оставалось пусто.
   *
   * У разложенной на сплиты операции единой категории нет, и тогда
   * здесь null: подставлять одну из нескольких наугад хуже, чем не подставлять.
   */
  transactionCategory?: { id: number; name: string } | null;
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

export function ItemsEditor({ items, onChange, total, transactionCategory = null }: ItemsEditorProps) {
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
                    bound={item.product_id != null}
                    // Единица и категория строки переезжают в заводимый
                    // товар: человек их только что указал, и спрашивать
                    // второй раз в справочнике незачем.
                    unitId={item.unit_id ?? null}
                    categoryId={item.category_id ?? null}
                    fallbackCategory={transactionCategory}
                    onCreated={(product) => update(index, { name: product.name, product_id: product.id })}
                    onChange={(name) => update(index, { name, product_id: null })}
                    onPick={(product) =>
                      update(index, {
                        name: product.name,
                        product_id: product.id,
                        // Категория и единица — подсказки из справочника. В
                        // позиции их можно поменять, справочник от этого не
                        // меняется.
                        category_id: product.category_id,
                        unit_id: product.unit_id,
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
                <select
                  value={item.unit_id ?? ""}
                  onChange={(event) =>
                    update(index, { unit_id: event.target.value ? Number(event.target.value) : null })
                  }
                  className="rounded-md border border-border bg-surface-1 px-2 py-2 text-sm"
                >
                  <option value="">{t("items.unit")}</option>
                  {(units ?? []).map((unit) => (
                    <option key={unit.id} value={unit.id}>
                      {unit.name}
                    </option>
                  ))}
                </select>
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
 * Выбор товара подставляет категорию и единицу — ради этого справочник и
 * заведён: человек перестаёт выбирать из списка в полторы сотни
 * подкатегорий, который всё равно не помнит наизусть.
 */
function ProductNameField({
  value,
  bound,
  unitId,
  categoryId,
  fallbackCategory,
  onChange,
  onPick,
  onCreated,
}: {
  value: string;
  /** Уже привязан к товару из справочника. */
  bound: boolean;
  unitId: number | null;
  categoryId: number | null;
  /** Категория операции — предлагается товару, когда своей у позиции нет. */
  fallbackCategory: { id: number; name: string } | null;
  onChange: (value: string) => void;
  onPick: (product: Product) => void;
  onCreated: (product: Product) => void;
}) {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const createProduct = useCreateProduct();
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

  const name = value.trim();
  // Предложение завести товар — когда набранное имя ни с чем не совпало.
  // Регулярные покупки почти всегда впервые вписываются здесь, в чеке, а
  // не в справочнике: уходить за этим на другую страницу посреди ввода
  // операции никто не станет, и товар просто не заводится никогда.
  const canCreate =
    !bound &&
    name.length >= 2 &&
    !createProduct.isPending &&
    !suggestions.some((product) => product.name.toLowerCase() === name.toLowerCase());

  async function create() {
    let category = categoryId;
    if (category === null && fallbackCategory !== null) {
      // Товар, заведённый прямо в чеке, оставался без категории. Своей
      // категории у позиции обычно нет — она и так берётся у операции, — и
      // в справочник переезжало пустое поле. В следующем чеке подставлять
      // становилось нечего — ради этого справочник и заведён.
      //
      // Спрашиваем, а не подставляем молча: категория операции подходит
      // товару не всегда. Обед из «Столовой» — это «Столовая» у похода,
      // а не у самого обеда.
      const assign = await confirm({
        message: t("items.assignCategoryToProduct", { name, category: fallbackCategory.name }),
        confirmLabel: t("items.assignCategoryYes"),
        cancelLabel: t("items.assignCategoryNo"),
      });
      if (assign) category = fallbackCategory.id;
    }
    const product = await createProduct.mutateAsync({
      name,
      unit_id: unitId,
      category_id: category,
      barcode: null,
      notes: null,
    });
    onCreated(product);
    setOpen(false);
  }

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
      {open && (suggestions.length > 0 || canCreate) && (
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
                {product.category_name && (
                  <span className="shrink-0 text-xs text-text-muted">{product.category_name}</span>
                )}
              </button>
            </li>
          ))}
          {canCreate && (
            <li className={suggestions.length > 0 ? "border-t border-border" : undefined}>
              <button
                type="button"
                // pointerdown, а не click: поле теряет фокус раньше, чем
                // click успевает дойти, и подсказка закрывается пустой.
                onPointerDown={(event) => {
                  event.preventDefault();
                  void create();
                }}
                className="flex w-full items-center gap-1.5 px-3 py-1.5 text-left text-sm text-series-1 hover:bg-surface-2"
              >
                <Plus size={13} className="shrink-0" />
                <span className="truncate">{t("items.createProduct", { name })}</span>
              </button>
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
