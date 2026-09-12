import { useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Dialog } from "@/components/ui/Dialog";
import { usePriceHistory } from "@/hooks/useProducts";
import { useTranslation } from "@/lib/i18n";
import { formatCurrency, formatTransactionDate } from "@/lib/format";
import type { PriceSeries, Product } from "@/types";
import { ChartTooltipBox } from "@/components/charts/ChartTooltipBox";

interface PriceHistoryModalProps {
  product: Product | null;
  onClose: () => void;
}

/**
 * Динамика цены товара.
 *
 * Цена — за базовую меру своего рода: килограмм, литр, штука. Без этого
 * приведения «1,5 л за 120 ₽» и «500 мл за 55 ₽» несравнимы, а именно на
 * этом и сгорели колонки количества в исходной таблице — там единицы были
 * подписями без арифметики, и заполнены они оказались в 11% записей.
 *
 * Кривых столько, сколько мер у товара встретилось, и переключаются они
 * сверху. Складывать их в одну нельзя: штука и килограмм — разные
 * величины, и общий график из них показывал падение цены на 91% там, где
 * человек просто записал покупку по-другому. Разные меры у одного товара —
 * обычное дело: сегодня «1 упаковка», завтра «900 г».
 *
 * Позиции без цены или количества в график не попадают: это воспоминание, а
 * не измерение. Но и молчать о них нельзя — иначе непонятно, почему
 * покупок восемь, а точек пять.
 */
export function PriceHistoryModal({ product, onClose }: PriceHistoryModalProps) {
  const { t } = useTranslation();
  const { data: history, isLoading } = usePriceHistory(product?.id ?? null);
  // Какая кривая открыта. Индекс, а не мера: сервер уже отсортировал их по
  // числу покупок, и нулевая — та, которой человек пользуется.
  const [active, setActive] = useState(0);

  const series = history?.series ?? [];
  const current = series[Math.min(active, Math.max(series.length - 1, 0))];

  return (
    <Dialog open={product !== null} onClose={onClose} title={product?.name ?? ""}>
      {isLoading || !history ? (
        <p className="py-10 text-center text-sm text-text-muted">{t("common.loading")}</p>
      ) : !current ? (
        <p className="py-10 text-center text-sm text-text-muted">{t("product.noPrices")}</p>
      ) : (
        <div className="space-y-4">
          {/* Переключатель мер — только когда их правда несколько: одна
              кнопка над графиком заставляет искать вторую. */}
          {series.length > 1 && (
            <div className="flex flex-wrap gap-1">
              {series.map((item, index) => (
                <button
                  key={item.unit_kind ?? index}
                  type="button"
                  onClick={() => setActive(index)}
                  className={`rounded-md border px-2 py-1 text-xs transition-colors ${
                    index === active
                      ? "border-accent bg-accent/15 text-text-primary"
                      : "border-border text-text-muted hover:bg-surface-2 hover:text-text-primary"
                  }`}
                >
                  {seriesLabel(item, t)} · {item.points.length}
                </button>
              ))}
            </div>
          )}

          <SeriesView series={current} />

          {/* Покупки, по которым цену за меру посчитать не из чего. Строка
              появляется, только когда такие есть. */}
          {history.unmeasured > 0 && (
            <p className="text-xs text-text-muted">
              {t("product.unmeasured", { count: history.unmeasured })}
            </p>
          )}
        </div>
      )}
    </Dialog>
  );
}

type Translate = ReturnType<typeof useTranslation>["t"];

/** Подпись меры: «₽ / кг». Без базовой единицы — общая формулировка. */
function seriesLabel(series: PriceSeries, t: Translate): string {
  return series.base_unit_name
    ? t("product.perUnit", { unit: series.base_unit_name })
    : t("product.perBaseUnit");
}

/** «× 0,9 л» — приписка к количеству, когда размер упаковки был записан. */
function packLabel(size: string | null, unit: string | null): string {
  if (!size || !unit) return "";
  return ` × ${Number(size)} ${unit}`;
}

/** Одна кривая: числа, график и список покупок в этой мере. */
function SeriesView({ series }: { series: PriceSeries }) {
  const { t } = useTranslation();
  const unitLabel = seriesLabel(series, t);

  const chartData = series.points.map((point) => ({
    date: point.date,
    price: Number(point.price_per_base_unit),
    store: point.store_name,
    quantity: point.quantity,
    unit: point.unit_name,
    pack: packLabel(point.pack_size, point.pack_unit_name),
    amount: point.amount,
  }));

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3 text-sm">
        <Stat label={t("product.lastPrice")} value={series.last_price} unit={unitLabel} />
        <Stat label={t("product.minPrice")} value={series.min_price} unit={unitLabel} />
        <Stat label={t("product.maxPrice")} value={series.max_price} unit={unitLabel} />
      </div>

      {series.change_percent !== null && (
        <p className="text-sm">
          <span
            className={
              series.change_percent > 0
                ? "font-medium text-danger"
                : series.change_percent < 0
                  ? "font-medium text-success"
                  : "text-text-muted"
            }
          >
            {series.change_percent > 0 ? "+" : ""}
            {series.change_percent}%
          </span>{" "}
          <span className="text-text-muted">{t("product.changeSinceFirst")}</span>
        </p>
      )}

      {/* Одна точка — не кривая. Показывать линию из одной покупки
          значило бы обещать динамику там, где её ещё нет. */}
      {chartData.length > 1 && (
        <div className="h-48 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 5, right: 5, bottom: 5, left: 5 }}>
              <CartesianGrid stroke="var(--gridline)" vertical={false} />
              <XAxis
                dataKey="date"
                tickFormatter={(value: string) => formatTransactionDate(value)}
                tick={{ fontSize: 11, fill: "var(--text-muted)" }}
                stroke="var(--gridline)"
              />
              <YAxis
                tick={{ fontSize: 11, fill: "var(--text-muted)" }}
                stroke="var(--gridline)"
                width={56}
              />
              <Tooltip
                isAnimationActive={false}
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const point = payload[0].payload as (typeof chartData)[number];
                  return (
                    <ChartTooltipBox className="text-xs">
                      <p className="text-text-muted">{formatTransactionDate(point.date, true)}</p>
                      <p className="font-medium text-text-primary">
                        {formatCurrency(point.price)} {unitLabel}
                      </p>
                      <p className="text-text-muted">
                        {point.quantity} {point.unit ?? ""}
                        {point.pack} · {formatCurrency(point.amount)}
                      </p>
                      {point.store && <p className="text-text-muted">{point.store}</p>}
                    </ChartTooltipBox>
                  );
                }}
              />
              <Line
                type="monotone"
                dataKey="price"
                stroke="var(--series-1)"
                strokeWidth={2}
                dot={{ r: 3 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      <ul className="max-h-48 divide-y divide-gridline overflow-y-auto text-sm">
        {series.points
          .slice()
          .reverse()
          .map((point) => (
            <li key={point.transaction_id} className="flex items-center justify-between gap-3 py-1.5">
              <span className="min-w-0">
                <span className="block text-text-secondary">
                  {formatTransactionDate(point.date, true)}
                </span>
                <span className="block truncate text-xs text-text-muted">
                  {point.quantity} {point.unit_name ?? ""}
                  {packLabel(point.pack_size, point.pack_unit_name)}
                  {point.store_name && ` · ${point.store_name}`}
                </span>
              </span>
              <span className="shrink-0 text-right">
                <span className="block tabular-nums">{formatCurrency(point.amount)}</span>
                <span className="block text-xs tabular-nums text-text-muted">
                  {formatCurrency(point.price_per_base_unit)} {unitLabel}
                </span>
              </span>
            </li>
          ))}
      </ul>
    </div>
  );
}

function Stat({ label, value, unit }: { label: string; value: string | null; unit: string }) {
  return (
    <div className="rounded-lg border border-border p-2.5">
      <p className="text-xs text-text-muted">{label}</p>
      <p className="mt-0.5 tabular-nums">{value === null ? "—" : formatCurrency(value)}</p>
      <p className="text-[11px] text-text-muted">{unit}</p>
    </div>
  );
}
