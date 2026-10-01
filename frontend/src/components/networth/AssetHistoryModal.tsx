import { useState } from "react";
import { Check, Pencil, Trash2, X } from "lucide-react";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Dialog } from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ChartTooltipBox } from "@/components/charts/ChartTooltipBox";
import { LINE_CURSOR } from "@/components/charts/cursors";
import { useConfirm } from "@/components/ui/ConfirmProvider";
import {
  useAssetValuations,
  useDeleteAssetValuation,
  useUpdateAssetValuation,
} from "@/hooks/useAssets";
import { formatCurrency, formatTransactionDate, getIntlLocale } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import type { Asset, AssetValuation } from "@/types";

/**
 * История переоценок имущества: сколько оно стоило и когда.
 *
 * Жила в форме правки актива списком с крестиком — ошибку ввода можно было
 * убрать, а исправить нельзя, и графика не было вовсе. Между тем это ровно
 * та же история, что у цели: ряд точек во времени. Поэтому и устроена
 * теперь так же — отдельным окном с графиком, правкой и удалением.
 *
 * График здесь не лесенка, как у цели, и это не мелочь. Взнос в цель —
 * прибавка, и осмысленная линия одна: накоплено на дату. А цена — это
 * состояние: компьютер в кризис памяти дорожает, машина с годами дешевеет,
 * и линия между точками значит «как менялось». Прямая, а не сглаженная:
 * сглаживание пририсовало бы колебания, которых между двумя оценками никто
 * не наблюдал.
 */
export function AssetHistoryModal({ asset, onClose }: { asset: Asset | null; onClose: () => void }) {
  const { t } = useTranslation();
  const { data: history, isLoading } = useAssetValuations(asset?.id ?? null);

  return (
    <Dialog open={asset !== null} onClose={onClose} title={asset?.name ?? ""} wide>
      {asset === null ? null : isLoading ? (
        <p className="py-10 text-center text-sm text-text-muted">…</p>
      ) : (history ?? []).length === 0 ? (
        <p className="py-10 text-center text-sm text-text-muted">{t("netWorth.history.empty")}</p>
      ) : (
        <div className="space-y-4">
          <p className="text-xs text-text-muted">{t("netWorth.form.historyHint")}</p>
          <PriceChart asset={asset} history={history ?? []} />
          <HistoryTable asset={asset} history={history ?? []} />
        </div>
      )}
    </Dialog>
  );
}

/** Подпись оси: день и месяц. Год не влезает и почти всегда один и тот же —
 *  полная дата читается в подсказке. */
function axisDate(iso: string): string {
  return new Intl.DateTimeFormat(getIntlLocale(), { day: "numeric", month: "short" }).format(
    new Date(`${iso}T00:00:00`)
  );
}

function PriceChart({ asset, history }: { asset: Asset; history: AssetValuation[] }) {
  // По одной точке линию не проводят: она покажет не «как менялось», а
  // «сколько стоит», — а это и так написано в списке под графиком.
  if (history.length < 2) return null;

  const data = history.map((point) => ({
    date: point.as_of_date,
    value: Number(point.value),
  }));

  return (
    <div className="chart-palette h-44 w-full sm:h-52">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 5, right: 5, bottom: 5, left: 5 }}>
          <XAxis
            dataKey="date"
            tickFormatter={axisDate}
            tick={{ fontSize: 11, fill: "var(--text-muted)" }}
            stroke="var(--gridline)"
            interval="preserveStartEnd"
            minTickGap={24}
          />
          {/* Ось не от нуля: цена имущества колеблется в своём диапазоне, и
              растянутая до нуля шкала превращает любое колебание в прямую. */}
          <YAxis
            domain={["auto", "auto"]}
            tick={{ fontSize: 11, fill: "var(--text-muted)" }}
            stroke="var(--gridline)"
            width={60}
            tickFormatter={(value: number) =>
              new Intl.NumberFormat(getIntlLocale(), {
                notation: "compact",
                maximumFractionDigits: 1,
              }).format(value)
            }
          />
          <Tooltip
            isAnimationActive={false}
            cursor={LINE_CURSOR}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const point = payload[0].payload as (typeof data)[number];
              return (
                <ChartTooltipBox className="text-xs">
                  <p className="text-text-muted">{formatTransactionDate(point.date, true)}</p>
                  <p className="font-medium text-text-primary">
                    {formatCurrency(point.value, asset.currency)}
                  </p>
                </ChartTooltipBox>
              );
            }}
          />
          <Line
            type="linear"
            dataKey="value"
            stroke="var(--accent)"
            strokeWidth={2}
            dot={{ r: 3, strokeWidth: 0, fill: "var(--accent)" }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function HistoryTable({ asset, history }: { asset: Asset; history: AssetValuation[] }) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState<number | null>(null);
  // Сверху свежее: последняя цена — та, которую ищут чаще всего.
  const rows = [...history].reverse();
  const latest = history[history.length - 1];

  return (
    <ul className="divide-y divide-gridline">
      {rows.map((row) =>
        editing === row.id ? (
          <EditRow key={row.id} asset={asset} row={row} onDone={() => setEditing(null)} />
        ) : (
          <ViewRow
            key={row.id}
            asset={asset}
            row={row}
            onEdit={() => setEditing(row.id)}
            onlyOne={history.length <= 1}
          />
        )
      )}
      <li className="pt-2 text-right text-xs text-text-muted">
        {t("netWorth.history.current", {
          amount: formatCurrency(latest?.value ?? 0, asset.currency),
        })}
      </li>
    </ul>
  );
}

function ViewRow({
  asset,
  row,
  onEdit,
  onlyOne,
}: {
  asset: Asset;
  row: AssetValuation;
  onEdit: () => void;
  /** Единственную оценку убрать нельзя: актив без цены не показать нигде,
   *  и вместо исправленной ошибки получился бы актив-невидимка. */
  onlyOne: boolean;
}) {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const removeValuation = useDeleteAssetValuation();

  async function handleDelete() {
    const ok = await confirm({
      message: t("netWorth.history.confirmDelete", {
        date: formatTransactionDate(row.as_of_date, true),
      }),
      confirmLabel: t("common.delete"),
      tone: "danger",
    });
    if (ok) removeValuation.mutate({ id: asset.id, valuationId: row.id });
  }

  return (
    <li className="flex items-center gap-3 py-2">
      <span className="min-w-0 flex-1 text-sm">{formatTransactionDate(row.as_of_date, true)}</span>
      <span className="shrink-0 text-sm font-medium tabular-nums text-text-primary">
        {formatCurrency(row.value, asset.currency)}
      </span>
      <span className="flex shrink-0 gap-1">
        <button
          type="button"
          onClick={onEdit}
          aria-label={t("common.edit")}
          className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
        >
          <Pencil size={15} />
        </button>
        <button
          type="button"
          onClick={handleDelete}
          disabled={onlyOne || removeValuation.isPending}
          aria-label={t("common.delete")}
          title={onlyOne ? t("netWorth.history.onlyOne") : t("common.delete")}
          className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-danger disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Trash2 size={15} />
        </button>
      </span>
    </li>
  );
}

function EditRow({
  asset,
  row,
  onDone,
}: {
  asset: Asset;
  row: AssetValuation;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const saveValuation = useUpdateAssetValuation();
  const [value, setValue] = useState(row.value);
  const [date, setDate] = useState(row.as_of_date);
  const [error, setError] = useState<string | null>(null);

  function handleSave() {
    setError(null);
    saveValuation.mutate(
      { id: asset.id, valuationId: row.id, input: { value, as_of_date: date } },
      {
        onSuccess: onDone,
        // День у оценки один: перенос на занятую дату сервер отклоняет, и
        // человеку надо сказать почему, а не просто ничего не сделать.
        onError: () => setError(t("netWorth.history.dateTaken")),
      }
    );
  }

  return (
    <li className="grid grid-cols-2 items-center gap-2 py-2 sm:grid-cols-[10rem_minmax(0,1fr)_auto]">
      <Input
        type="date"
        value={date}
        onChange={(event) => setDate(event.target.value)}
        className="w-full min-w-0"
      />
      <Input
        type="number"
        step="0.01"
        min="0"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        className="w-full min-w-0"
      />
      <span className="col-span-2 flex justify-end gap-2 sm:col-span-1">
        <Button type="button" onClick={handleSave} disabled={saveValuation.isPending}>
          <Check size={15} />
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          <X size={15} />
        </Button>
      </span>
      {error && <p className="col-span-2 text-xs text-danger sm:col-span-3">{error}</p>}
    </li>
  );
}
