import { AlertTriangle } from "lucide-react";
import { useTranslation } from "@/lib/i18n";
import { formatCurrency, formatSignedCurrency } from "@/lib/format";
import type { InvestmentHolding } from "@/types";

interface HoldingListProps {
  items: InvestmentHolding[];
  onOpen: (holding: InvestmentHolding) => void;
}

/**
 * Список позиций.
 *
 * Порядок задаёт бэкенд: сначала то, во что вложено больше денег, а не то,
 * что дороже стоит сейчас. Список отвечает на вопрос «где мои деньги», и
 * позиция, выросшая втрое, не важнее той, в которую вложено втрое больше.
 */
export function HoldingList({ items, onOpen }: HoldingListProps) {
  const { t } = useTranslation();

  if (items.length === 0) {
    return <p className="py-10 text-center text-sm text-text-muted">{t("investments.empty")}</p>;
  }

  return (
    <ul className="divide-y divide-gridline">
      {items.map((holding) => {
        const unrealised = holding.unrealised === null ? null : Number(holding.unrealised);
        const realised = Number(holding.realised);
        return (
          <li key={holding.id}>
            <button
              type="button"
              onClick={() => onOpen(holding)}
              className="flex w-full items-center gap-3 py-2.5 text-left hover:bg-surface-2/40"
            >
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-1.5 truncate text-sm font-medium text-text-primary">
                  {holding.ticker ?? holding.name}
                  {/* Продано больше, чем куплено — пропуск в данных.
                      Показывается значком, а не прячется: молчание тут
                      означало бы, что расчёт верен, а он неполон. */}
                  {Number(holding.oversold) > 0 && (
                    <AlertTriangle size={13} className="shrink-0 text-danger" />
                  )}
                </span>
                <span className="block truncate text-xs text-text-muted">
                  {holding.quantity} ×{" "}
                  {holding.average_cost
                    ? formatCurrency(holding.average_cost, holding.currency)
                    : "—"}
                  {realised !== 0 && ` · ${t("investments.realisedShort")} ${formatSignedCurrency(realised)}`}
                </span>
              </span>

              <span className="shrink-0 text-right">
                {/* Прочерк, а не ноль: цена неизвестна — не значит, что актив
                    обесценился. */}
                <span className="block text-sm font-medium tabular-nums">
                  {/* В валюте самой бумаги: акция, купленная за доллары,
                      стоит столько долларов. */}
                  {holding.value === null ? "—" : formatCurrency(holding.value, holding.currency)}
                </span>
                {unrealised !== null && (
                  <span
                    className={`block text-xs tabular-nums ${
                      unrealised > 0 ? "text-success" : unrealised < 0 ? "text-danger" : "text-text-muted"
                    }`}
                  >
                    {formatSignedCurrency(unrealised)}
                    {holding.unrealised_percent !== null && ` (${holding.unrealised_percent > 0 ? "+" : ""}${holding.unrealised_percent}%)`}
                  </span>
                )}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
