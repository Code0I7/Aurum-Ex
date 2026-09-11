import { Archive, ArchiveRestore, LineChart, Pencil, Trash2 } from "lucide-react";
import { useTranslation } from "@/lib/i18n";
import { formatCurrency, formatTransactionDate } from "@/lib/format";
import type { Product } from "@/types";

interface ProductListProps {
  items: Product[];
  onEdit: (product: Product) => void;
  onPrices: (product: Product) => void;
  onDelete: (product: Product) => void;
  /** Убрать из подсказок при вводе, не теряя историю цен. */
  onArchive: (product: Product) => void;
}

export function ProductList({ items, onEdit, onPrices, onDelete, onArchive }: ProductListProps) {
  const { t } = useTranslation();

  if (items.length === 0) {
    return <p className="py-10 text-center text-sm text-text-muted">{t("product.empty")}</p>;
  }

  return (
    <ul className="divide-y divide-gridline">
      {items.map((product) => (
        <li key={product.id} className={`flex items-center gap-3 py-2.5 ${product.is_archived ? "opacity-50" : ""}`}>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium text-text-primary">{product.name}</span>
            <span className="block truncate text-xs text-text-muted">
              {product.unit_name ?? t("product.noUnit")}
              {/* Сколько раз покупали и когда в последний раз: без этого
                  список товаров — просто список слов, и непонятно, что живое,
                  а что заведено однажды по ошибке. */}
              {product.purchases > 0
                ? ` · ${t("product.purchases", { count: product.purchases })}`
                : ` · ${t("product.neverBought")}`}
              {product.last_bought && ` · ${formatTransactionDate(product.last_bought, true)}`}
            </span>
          </span>

          {/* Две разные цифры, и обе нужны. Цена за базовую единицу
              отвечает «дорожает ли», сумма за год — «сколько мне это
              стоит»: полтинник за батон незаметен, три тысячи за год на
              хлеб — уже разговор. */}
          <span className="shrink-0 text-right">
            {Number(product.spent_year) > 0 && (
              <span className="block text-sm tabular-nums text-text-primary">
                {formatCurrency(product.spent_year)}
                <span className="ml-1 text-xs font-normal text-text-muted">
                  {t("product.perYear")}
                </span>
              </span>
            )}
            {product.last_price_per_base_unit && (
              <span className="block text-xs tabular-nums text-text-muted">
                {formatCurrency(product.last_price_per_base_unit)}
                {product.base_unit_name && ` / ${product.base_unit_name}`}
              </span>
            )}
          </span>

          <span className="flex shrink-0 gap-1">
            {/* График цены предлагается только когда точек хватает: кнопка,
                открывающая пустое окно, обещает то, чего нет. */}
            {product.purchases > 0 && (
              <button
                type="button"
                aria-label={t("product.priceHistory")}
                onClick={() => onPrices(product)}
                className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
              >
                <LineChart size={15} />
              </button>
            )}
            <button
              type="button"
              aria-label={t("common.edit")}
              onClick={() => onEdit(product)}
              className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
            >
              <Pencil size={15} />
            </button>
            {/* Архив, а не удаление: у товара есть история цен, привязанная
                к позициям чеков. Убрать его из подсказок при вводе почти
                всегда и есть то, чего человек хочет. */}
            <button
              type="button"
              aria-label={product.is_archived ? t("product.restore") : t("product.archive")}
              title={product.is_archived ? t("product.restore") : t("product.archive")}
              onClick={() => onArchive(product)}
              className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
            >
              {product.is_archived ? <ArchiveRestore size={15} /> : <Archive size={15} />}
            </button>
            <button
              type="button"
              aria-label={t("common.delete")}
              onClick={() => onDelete(product)}
              className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-danger"
            >
              <Trash2 size={15} />
            </button>
          </span>
        </li>
      ))}
    </ul>
  );
}
