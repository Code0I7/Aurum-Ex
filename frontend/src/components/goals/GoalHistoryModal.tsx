import { useState } from "react";
import { Check, Pencil, Trash2, X } from "lucide-react";
import {
  Area,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Dialog } from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ChartTooltipBox } from "@/components/charts/ChartTooltipBox";
import { LINE_CURSOR } from "@/components/charts/cursors";
import { useConfirm } from "@/components/ui/ConfirmProvider";
import {
  useDeleteGoalContribution,
  useGoalContributions,
  useUpdateGoalContribution,
} from "@/hooks/useGoals";
import { formatCurrency, formatTransactionDate, getIntlLocale } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import type { Goal, GoalContribution } from "@/types";

/**
 * История накопления цели: как набралась нынешняя сумма.
 *
 * График здесь не такой, как у кривой цены товара, и это не случайность. У
 * товара точки — независимые цены в разные дни, и линия между ними значит
 * «как менялось». У цели взнос — не состояние, а прибавка, и осмысленная
 * линия ровно одна: накоплено на дату. Поэтому лесенка вверх, а выносы —
 * ступеньки вниз.
 *
 * Вторая линия — план: прямая от нуля в день начала до целевой суммы в
 * планируемый день. Ради неё планируемая дата и заводилась: «отстаю или
 * иду с опережением» видно глазом, а не считается в уме. Нет хотя бы одной
 * из двух дат — нет и линии: провести её наугад значит выдумать обещание,
 * которого человек не давал.
 */
export function GoalHistoryModal({ goal, onClose }: { goal: Goal | null; onClose: () => void }) {
  const { t } = useTranslation();
  const { data: history, isLoading } = useGoalContributions(goal?.id ?? null);

  return (
    <Dialog open={goal !== null} onClose={onClose} title={goal?.name ?? ""} wide>
      {goal === null ? null : isLoading ? (
        <p className="py-10 text-center text-sm text-text-muted">…</p>
      ) : (history ?? []).length === 0 ? (
        <p className="py-10 text-center text-sm text-text-muted">{t("goal.history.empty")}</p>
      ) : (
        <div className="space-y-4">
          <SavingsChart goal={goal} history={history ?? []} />
          <HistoryTable goal={goal} history={history ?? []} />
        </div>
      )}
    </Dialog>
  );
}

interface ChartPoint {
  date: string;
  saved: number;
  /** Где следовало бы быть по плану в этот день. null вне срока плана и
   *  когда плана нет вовсе. */
  plan: number | null;
}

function buildPlan(goal: Goal, date: string, target: number): number | null {
  if (!goal.started_on || !goal.planned_on) return null;
  const start = new Date(`${goal.started_on}T00:00:00`).getTime();
  const finish = new Date(`${goal.planned_on}T00:00:00`).getTime();
  if (finish <= start) return null;
  const at = new Date(`${date}T00:00:00`).getTime();
  // За пределами срока план не продолжается: «надо было накопить полторы
  // цели» — не обещание, а арифметика, вышедшая из берегов.
  const share = Math.min(Math.max((at - start) / (finish - start), 0), 1);
  return target * share;
}

function SavingsChart({ goal, history }: { goal: Goal; history: GoalContribution[] }) {
  const { t } = useTranslation();
  const target = Number(goal.target_amount);

  const points: ChartPoint[] = history.map((row) => ({
    date: row.date,
    saved: Number(row.running_total),
    plan: buildPlan(goal, row.date, target),
  }));

  // Линия плана без своей крайней точки обрывалась бы на последнем взносе,
  // даже если до срока ещё месяц. Дорисовываем планируемый день — по
  // накоплению там ничего не известно, и лесенка до него не тянется.
  if (goal.planned_on && points.length > 0 && goal.planned_on > points[points.length - 1].date) {
    points.push({ date: goal.planned_on, saved: NaN, plan: target });
  }

  return (
    <div className="h-52 w-full sm:h-64">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
          <XAxis
            dataKey="date"
            tick={{ fontSize: 11, fill: "var(--text-muted)" }}
            tickFormatter={(value: string) => formatTransactionDate(value)}
            axisLine={false}
            tickLine={false}
            minTickGap={24}
          />
          <YAxis
            tick={{ fontSize: 11, fill: "var(--text-muted)" }}
            tickFormatter={(value: number) =>
              new Intl.NumberFormat(getIntlLocale(), { notation: "compact" }).format(value)
            }
            axisLine={false}
            tickLine={false}
            width={48}
          />
          {/* Цель — горизонтальная черта, а не верхний край: видно не
              только «сколько накоплено», но и сколько ещё до верха. */}
          <ReferenceLine
            y={target}
            stroke="var(--text-muted)"
            strokeDasharray="4 4"
            label={{
              value: t("goal.history.target"),
              position: "insideTopRight",
              fill: "var(--text-muted)",
              fontSize: 11,
            }}
          />
          {goal.started_on && goal.planned_on && (
            <Line
              type="linear"
              dataKey="plan"
              stroke="var(--text-muted)"
              strokeDasharray="3 3"
              strokeWidth={1.5}
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
          )}
          {/* Ступенчатая, а не сглаженная: между взносами ничего не
              происходило, и плавный подъём рисовал бы накопление, которого
              в те дни не было. */}
          <Area
            type="stepAfter"
            dataKey="saved"
            stroke="var(--success)"
            strokeWidth={2}
            fill="var(--success)"
            fillOpacity={0.12}
            dot={{ r: 2.5, fill: "var(--success)" }}
            isAnimationActive={false}
            connectNulls
          />
          <Tooltip
            isAnimationActive={false}
            cursor={LINE_CURSOR}
            content={<SavingsTooltip />}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

function SavingsTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: ChartPoint }>;
}) {
  const { t } = useTranslation();
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <ChartTooltipBox>
      <p className="text-text-muted">{formatTransactionDate(point.date, true)}</p>
      {Number.isFinite(point.saved) && (
        <p className="font-medium tabular-nums text-text-primary">
          {t("goal.history.saved")}: {formatCurrency(point.saved)}
        </p>
      )}
      {point.plan !== null && (
        <p className="tabular-nums text-text-secondary">
          {t("goal.history.plan")}: {formatCurrency(point.plan)}
        </p>
      )}
    </ChartTooltipBox>
  );
}

function HistoryTable({ goal, history }: { goal: Goal; history: GoalContribution[] }) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState<number | null>(null);

  return (
    <ul className="divide-y divide-gridline">
      {history.map((row) =>
        editing === row.id ? (
          <EditRow key={row.id} goal={goal} row={row} onDone={() => setEditing(null)} />
        ) : (
          <ViewRow key={row.id} goal={goal} row={row} onEdit={() => setEditing(row.id)} />
        )
      )}
      <li className="pt-2 text-right text-xs text-text-muted">
        {t("goal.history.total", {
          amount: formatCurrency(history[history.length - 1]?.running_total ?? 0),
        })}
      </li>
    </ul>
  );
}

function ViewRow({
  goal,
  row,
  onEdit,
}: {
  goal: Goal;
  row: GoalContribution;
  onEdit: () => void;
}) {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const removeContribution = useDeleteGoalContribution();
  const amount = Number(row.amount);
  // Взнос, привязанный к трате, объясняет, куда делись отложенные деньги.
  // Убрать его — оставить покупку без объяснения, а цель с деньгами,
  // которых на счёте давно нет. Править его при этом можно.
  const locked = row.transaction_id !== null;

  async function handleDelete() {
    const ok = await confirm({
      message: t("goal.history.confirmDelete", { amount: formatCurrency(Math.abs(amount)) }),
      confirmLabel: t("common.delete"),
      tone: "danger",
    });
    if (ok) removeContribution.mutate({ goalId: goal.id, contributionId: row.id });
  }

  return (
    <li className="flex items-center gap-3 py-2">
      <span className="min-w-0 flex-1">
        <span className="block text-sm">{formatTransactionDate(row.date, true)}</span>
        <span className="block truncate text-xs text-text-muted">
          {[row.note, row.account_name].filter(Boolean).join(" · ") || t("goal.history.noNote")}
        </span>
      </span>
      <span
        className="shrink-0 text-sm font-medium tabular-nums"
        style={{ color: amount < 0 ? "var(--danger)" : "var(--success)" }}
      >
        {amount > 0 ? "+" : "−"}
        {formatCurrency(Math.abs(amount))}
      </span>
      <span className="w-24 shrink-0 text-right text-xs tabular-nums text-text-muted">
        {formatCurrency(row.running_total)}
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
          disabled={locked || removeContribution.isPending}
          aria-label={t("common.delete")}
          title={locked ? t("goal.history.tiedToPurchase") : t("common.delete")}
          className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-danger disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Trash2 size={15} />
        </button>
      </span>
    </li>
  );
}

function EditRow({
  goal,
  row,
  onDone,
}: {
  goal: Goal;
  row: GoalContribution;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const saveContribution = useUpdateGoalContribution();
  const [amount, setAmount] = useState(row.amount);
  const [date, setDate] = useState(row.date);
  const [note, setNote] = useState(row.note ?? "");

  function handleSave() {
    saveContribution.mutate(
      {
        goalId: goal.id,
        contributionId: row.id,
        input: { amount, date, note: note.trim() || null },
      },
      { onSuccess: onDone }
    );
  }

  return (
    <li className="flex flex-wrap items-center gap-2 py-2">
      <Input
        type="date"
        value={date}
        onChange={(event) => setDate(event.target.value)}
        className="w-40"
      />
      {/* Знак минуса вводится руками, как и при создании: вынос — это тот
          же взнос в другую сторону, а не отдельная кнопка. */}
      <Input
        type="number"
        step="0.01"
        value={amount}
        onChange={(event) => setAmount(event.target.value)}
        className="w-32"
      />
      <Input
        value={note}
        placeholder={t("goal.history.noNote")}
        onChange={(event) => setNote(event.target.value)}
        className="min-w-0 flex-1"
      />
      <Button type="button" onClick={handleSave} disabled={saveContribution.isPending}>
        <Check size={15} />
      </Button>
      <Button type="button" variant="ghost" onClick={onDone}>
        <X size={15} />
      </Button>
    </li>
  );
}
