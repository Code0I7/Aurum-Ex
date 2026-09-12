import { RefreshCw } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { useRates, useSyncRates } from "@/hooks/useCurrencies";
import { CURRENCIES } from "@/lib/currency";
import { formatRate, formatTransactionDate } from "@/lib/format";
import { useTranslation, type Language } from "@/lib/i18n";
import type { CurrencyRate } from "@/types";

/**
 * Курсы валют — сколько стоит доллар, евро, юань в валюте установки.
 *
 * Показываются те, за которыми человек следит, плюс те, что нужны расчётам:
 * валюта счёта попадает сюда сама, и убрать её из списка нельзя. Вопрос у
 * человека один — «сколько сейчас стоит», — и делить строки на «мои» и
 * «просто интересные» прямо на экране незачем.
 *
 * Курс здесь сегодняшний, а не на дату операции. Это две половины одного
 * правила: операция заморожена по курсу своего дня, а «сколько стоит
 * доллар» — вопрос про сейчас.
 */
export function RatesCard({ className }: {
  /** Высота задаётся снаружи: в сетке обзора карточка тянется до низа
   *  своей строки, иначе рядом с соседкой у неё разный нижний край. */
  className?: string;
}) {
  const { t, language } = useTranslation();
  const { data: rates, isLoading } = useRates();
  const sync = useSyncRates();

  // Дата самого свежего курса — по ней видно, насколько цифры устарели и
  // стоит ли жать обновление. Берётся максимум, а не первая попавшаяся:
  // валюты грузятся вместе, но у добранной задним числом дата своя.
  const freshest = (rates ?? [])
    .map((row) => row.rate_date)
    .filter((date): date is string => Boolean(date))
    .sort()
    .at(-1);

  return (
    <Card className={className}>
      <CardHeader className="items-start">
        <div className="min-w-0">
          <CardTitle>{t("dashboard.ratesTitle")}</CardTitle>
          {freshest && (
            <p className="mt-1 truncate text-xs text-text-muted">
              {t("dashboard.ratesAsOf", { date: formatTransactionDate(freshest, true) })}
            </p>
          )}
        </div>
        {/* Обновление стоит здесь, а не только в настройках: курс смотрят
            отсюда, и уходить за ним на другую вкладку человек не станет.
            Оно же досчитывает операции, которые этого курса ждали. */}
        <button
          type="button"
          onClick={() => sync.mutate()}
          disabled={sync.isPending}
          aria-label={t("dashboard.ratesRefresh")}
          title={t("dashboard.ratesRefresh")}
          className="shrink-0 rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary disabled:opacity-50"
        >
          <RefreshCw size={15} className={sync.isPending ? "animate-spin" : undefined} />
        </button>
      </CardHeader>
      <CardContent>
        {sync.isError && <p className="mb-2 text-xs text-danger">{t("dashboard.ratesSyncError")}</p>}
        {isLoading ? (
          <p className="py-6 text-center text-sm text-text-muted">…</p>
        ) : (rates ?? []).length === 0 ? (
          <p className="py-6 text-center text-sm text-text-muted">{t("dashboard.ratesEmpty")}</p>
        ) : (
          <ul className="divide-y divide-gridline">
            {(rates ?? []).map((row) => (
              <RateRow key={row.code} row={row} language={language} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

/** Название валюты без кода: код и так стоит первым. */
function currencyName(code: string, language: Language): string {
  const option = CURRENCIES.find((item) => item.code === code);
  if (!option) return code;
  return language === "ru" ? option.nameRu : option.nameEn;
}

function RateRow({ row, language }: { row: CurrencyRate; language: Language }) {
  const { t } = useTranslation();

  const change =
    row.rate !== null && row.previous !== null ? Number(row.rate) - Number(row.previous) : null;

  return (
    <li className="flex items-center justify-between gap-3 py-2">
      <span className="min-w-0">
        <span className="block truncate text-sm">
          <span className="font-medium">{row.code}</span>{" "}
          <span className="text-text-muted">{currencyName(row.code, language)}</span>
        </span>
        {/* Дата прошлого курса подписана к изменению, а не спрятана: курсы
            хранятся только за те дни, когда их грузили, и разница может
            оказаться не дневной, а трёхмесячной. */}
        {change !== null && change !== 0 && row.previous_date && (
          <span className="block truncate text-xs text-text-muted">
            {t("dashboard.ratesSince", { date: formatTransactionDate(row.previous_date, true) })}
          </span>
        )}
      </span>
      <span className="shrink-0 text-right">
        <span className="block text-sm font-medium tabular-nums">
          {row.rate === null ? t("dashboard.ratesUnknown") : formatRate(row.rate)}
        </span>
        {/* Вверх зелёное, вниз красное — как в любом приложении, где
            показывают курс. Значение у цвета здесь не «хорошо» и «плохо», а
            направление: спорить с привычкой, сложившейся у всех остальных,
            дороже, чем следовать ей. */}
        {change !== null && change !== 0 && (
          <span
            className="block text-xs tabular-nums"
            style={{ color: change > 0 ? "var(--success)" : "var(--danger)" }}
          >
            {change > 0 ? "↑ +" : "↓ −"}
            {formatRate(Math.abs(change))}
          </span>
        )}
      </span>
    </li>
  );
}
