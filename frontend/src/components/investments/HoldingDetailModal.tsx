import { useState } from "react";
import { Trash2 } from "lucide-react";
import { Dialog } from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { Input, Label } from "@/components/ui/Input";
import {
  useAddTrade,
  useDeleteTrade,
  useInvestmentHolding,
  useInvestmentTrades,
  useUpdateHolding,
} from "@/hooks/useInvestments";
import { useTranslation } from "@/lib/i18n";
import { formatCurrency, formatQuantity, formatSignedCurrency, formatTransactionDate } from "@/lib/format";
import type { TradeSide } from "@/types";

interface HoldingDetailModalProps {
  holdingId: number | null;
  onClose: () => void;
}

/**
 * Позиция целиком: цифры, открытые партии, история фиксаций, журнал сделок.
 *
 * Разнесение продаж по партиям показано намеренно — «продали то, что купили
 * в мае 2022-го» — ответ, который средневзвешенная дать не могла в принципе,
 * и ради которого метод и менялся.
 */
export function HoldingDetailModal({ holdingId, onClose }: HoldingDetailModalProps) {
  const { t } = useTranslation();
  const { data: holding } = useInvestmentHolding(holdingId);
  const { data: trades } = useInvestmentTrades(holdingId);
  const addTrade = useAddTrade();
  const deleteTrade = useDeleteTrade();
  const updateHolding = useUpdateHolding();

  const [side, setSide] = useState<TradeSide>("buy");
  const [quantity, setQuantity] = useState("");
  const [price, setPrice] = useState("");
  const [fee, setFee] = useState("");
  const [tradeDate, setTradeDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [manualPrice, setManualPrice] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submitTrade(event: React.FormEvent) {
    event.preventDefault();
    if (holdingId === null) return;
    setError(null);
    try {
      await addTrade.mutateAsync({
        holdingId,
        input: {
          side,
          quantity,
          price_per_unit: price,
          fee: fee || "0",
          trade_date: tradeDate,
        },
      });
      setQuantity("");
      setPrice("");
      setFee("");
    } catch {
      setError(t("investments.saveError"));
    }
  }

  async function savePrice() {
    if (holdingId === null || !manualPrice) return;
    await updateHolding.mutateAsync({ id: holdingId, input: { last_price: manualPrice } });
    setManualPrice("");
  }

  return (
    <Dialog open={holdingId !== null} onClose={onClose} title={holding?.name ?? ""}>
      {!holding ? (
        <p className="py-10 text-center text-sm text-text-muted">{t("common.loading")}</p>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Cell label={t("investments.quantity")} value={formatQuantity(holding.quantity)} />
            <Cell
              label={t("investments.averageCost")}
              value={
                holding.average_cost
                  ? formatCurrency(holding.average_cost, holding.currency)
                  : "—"
              }
            />
            <Cell
              label={t("investments.unrealised")}
              value={holding.unrealised === null ? "—" : formatSignedCurrency(holding.unrealised)}
              tone={
                holding.unrealised === null
                  ? undefined
                  : Number(holding.unrealised) >= 0
                    ? "success"
                    : "danger"
              }
            />
            <Cell
              label={t("investments.realised")}
              value={formatSignedCurrency(holding.realised)}
              tone={Number(holding.realised) >= 0 ? "success" : "danger"}
            />
          </div>

          {Number(holding.oversold) > 0 && (
            <p className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
              {t("investments.oversoldWarning", { quantity: formatQuantity(holding.oversold) })}
            </p>
          )}

          {/* Ручная переоценка. Внешних котировок у большинства бумаг нет, и
              вводить цену руками — нормальный путь, а не костыль. */}
          <div className="flex items-end gap-2">
            <div className="flex-1">
              <Label htmlFor="holding-price">{t("investments.currentPrice")}</Label>
              <Input
                id="holding-price"
                type="number"
                step="0.00000001"
                min="0"
                placeholder={holding.last_price ?? ""}
                value={manualPrice}
                onChange={(event) => setManualPrice(event.target.value)}
              />
            </div>
            <Button type="button" variant="secondary" onClick={savePrice} disabled={!manualPrice}>
              {t("common.save")}
            </Button>
          </div>
          {holding.last_price_at && (
            <p className="-mt-2 text-xs text-text-muted">
              {t("investments.pricedAt", { date: formatTransactionDate(holding.last_price_at.slice(0, 10), true) })}
            </p>
          )}

          <form onSubmit={submitTrade} className="space-y-2 rounded-lg border border-border p-3">
            <div className="flex gap-1">
              {(["buy", "sell"] as TradeSide[]).map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => setSide(item)}
                  className={`rounded-md px-3 py-1.5 text-xs font-medium ${
                    side === item
                      ? "bg-surface-2 text-text-primary"
                      : "text-text-muted hover:bg-surface-2 hover:text-text-primary"
                  }`}
                >
                  {t(`investments.${item}` as never)}
                </button>
              ))}
            </div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <Input
                type="number"
                step="0.00000001"
                min="0"
                required
                placeholder={t("investments.quantity")}
                value={quantity}
                onChange={(event) => setQuantity(event.target.value)}
              />
              <Input
                type="number"
                step="0.00000001"
                min="0"
                required
                placeholder={t("investments.price")}
                value={price}
                onChange={(event) => setPrice(event.target.value)}
              />
              <Input
                type="number"
                step="0.01"
                min="0"
                placeholder={t("investments.fee")}
                value={fee}
                onChange={(event) => setFee(event.target.value)}
              />
              <Input
                type="date"
                required
                value={tradeDate}
                onChange={(event) => setTradeDate(event.target.value)}
              />
            </div>
            <p className="text-xs text-text-muted">{t("investments.feeHint")}</p>
            {error && <p className="text-sm text-danger">{error}</p>}
            <div className="flex justify-end">
              <Button type="submit" disabled={addTrade.isPending}>
                {t("investments.addTrade")}
              </Button>
            </div>
          </form>

          {holding.open_lots.length > 0 && (
            <Section title={t("investments.openLots")} hint={t("investments.openLotsHint")}>
              <ul className="space-y-1 text-sm">
                {holding.open_lots.map((lot, index) => (
                  <li key={index} className="flex justify-between gap-3">
                    <span className="text-text-muted">
                      {lot.acquired_on ? formatTransactionDate(lot.acquired_on, true) : "—"}
                    </span>
                    <span className="tabular-nums">
                      {formatQuantity(lot.quantity)} × {formatCurrency(lot.cost_per_unit, holding.currency)}
                    </span>
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {holding.disposals.length > 0 && (
            <Section title={t("investments.disposals")} hint={t("investments.disposalsHint")}>
              <ul className="space-y-2 text-sm">
                {holding.disposals.map((disposal) => (
                  <li key={disposal.trade_id} className="rounded-md border border-border p-2">
                    <div className="flex justify-between gap-3">
                      <span className="text-text-muted">
                        {formatTransactionDate(disposal.trade_date, true)} · {formatQuantity(disposal.quantity)}
                      </span>
                      <span
                        className={`font-medium tabular-nums ${
                          Number(disposal.realised) >= 0 ? "text-success" : "text-danger"
                        }`}
                      >
                        {formatSignedCurrency(disposal.realised)}
                      </span>
                    </div>
                    <ul className="mt-1 space-y-0.5 text-xs text-text-muted">
                      {disposal.lots.map((lot, index) => (
                        <li key={index}>
                          {t("investments.fromLot", {
                            quantity: formatQuantity(lot.quantity),
                            price: formatCurrency(lot.cost_per_unit, holding.currency),
                            date: lot.acquired_on ? formatTransactionDate(lot.acquired_on, true) : "—",
                          })}
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
            </Section>
          )}

          <Section title={t("investments.trades")}>
            <ul className="max-h-48 divide-y divide-gridline overflow-y-auto text-sm">
              {(trades ?? []).map((trade) => (
                <li key={trade.id} className="flex items-center justify-between gap-2 py-1.5">
                  <span className="min-w-0">
                    <span className="block text-text-secondary">
                      {t(`investments.${trade.side}` as never)} {formatQuantity(trade.quantity)} ×{" "}
                      {formatCurrency(trade.price_per_unit, holding.currency)}
                    </span>
                    <span className="block text-xs text-text-muted">
                      {formatTransactionDate(trade.trade_date, true)}
                      {Number(trade.fee) > 0 &&
                        ` · ${t("investments.fee")} ${formatCurrency(trade.fee, holding.currency)}`}
                    </span>
                  </span>
                  <button
                    type="button"
                    aria-label={t("common.delete")}
                    onClick={() => deleteTrade.mutate(trade.id)}
                    className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-danger"
                  >
                    <Trash2 size={14} />
                  </button>
                </li>
              ))}
            </ul>
          </Section>
        </div>
      )}
    </Dialog>
  );
}

function Cell({ label, value, tone }: { label: string; value: string; tone?: "success" | "danger" }) {
  const color = tone === "success" ? "text-success" : tone === "danger" ? "text-danger" : "text-text-primary";
  return (
    <div className="rounded-md border border-border p-2">
      <p className="text-[11px] text-text-muted">{label}</p>
      <p className={`mt-0.5 text-sm font-medium tabular-nums ${color}`}>{value}</p>
    </div>
  );
}

function Section({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <p className="text-sm font-medium text-text-primary">{title}</p>
      {hint && <p className="mb-1.5 text-xs text-text-muted">{hint}</p>}
      <div className={hint ? "" : "mt-1.5"}>{children}</div>
    </div>
  );
}
