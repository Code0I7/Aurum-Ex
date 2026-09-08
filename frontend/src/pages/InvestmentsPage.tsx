import { useMemo, useState } from "react";
import { Pencil, Plus } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { HoldingList } from "@/components/investments/HoldingList";
import { HoldingFormModal } from "@/components/investments/HoldingFormModal";
import { HoldingDetailModal } from "@/components/investments/HoldingDetailModal";
import { PortfolioFormModal } from "@/components/investments/PortfolioFormModal";
import {
  useCreatePortfolio,
  useInvestmentHoldings,
  useInvestmentPortfolios,
} from "@/hooks/useInvestments";
import { useTranslation } from "@/lib/i18n";
import { formatCurrency, formatSignedCurrency } from "@/lib/format";
import type { InvestmentKind, InvestmentPortfolio } from "@/types";

const KINDS: Array<InvestmentKind | "all"> = ["all", "stock", "bond", "fund", "crypto", "metal", "other"];

/**
 * Инвестиции — один раздел на все семейства активов.
 *
 * Вкладка вида (акции, крипта, металлы) — это фильтр, а не отдельная
 * система: партии, стоимость владения и списание по FIFO устроены одинаково
 * для акции и для монеты, и разводить их значило бы обещать разницу,
 * которой нет.
 */
export function InvestmentsPage() {
  const { t } = useTranslation();
  const { data: portfolios } = useInvestmentPortfolios();
  const createPortfolio = useCreatePortfolio();
  const [portfolioModalOpen, setPortfolioModalOpen] = useState(false);
  const [editingPortfolio, setEditingPortfolio] = useState<InvestmentPortfolio | null>(null);
  const [portfolioId, setPortfolioId] = useState<number | null>(null);
  const [kind, setKind] = useState<InvestmentKind | "all">("all");
  const { data: holdings, isLoading } = useInvestmentHoldings(portfolioId ?? undefined);

  const [formOpen, setFormOpen] = useState(false);
  const [detailId, setDetailId] = useState<number | null>(null);

  const visible = useMemo(
    () => (holdings ?? []).filter((holding) => kind === "all" || holding.kind === kind),
    [holdings, kind],
  );

  const totals = useMemo(() => {
    // Стоимость складывает только то, у чего есть цена. Позиция без
    // котировки не считается нулевой — она просто не участвует в сумме, и
    // подпись об этом говорит.
    let value = 0;
    let priced = 0;
    let cost = 0;
    let realised = 0;
    for (const holding of visible) {
      cost += Number(holding.cost_basis);
      realised += Number(holding.realised);
      if (holding.value !== null) {
        value += Number(holding.value);
        priced += 1;
      }
    }
    return { value, cost, realised, priced, unpriced: visible.length - priced };
  }, [visible]);

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader className="items-start">
          <div>
            <CardTitle>{t("nav.investments")}</CardTitle>
            <p className="mt-1 text-xs text-text-muted">{t("investments.subtitle")}</p>
          </div>
          <Button onClick={() => setFormOpen(true)} disabled={(portfolios ?? []).length === 0}>
            <Plus size={16} />
            {t("common.add")}
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          {(portfolios ?? []).length === 0 ? (
            // Первый портфель заводится одной кнопкой: заставлять придумывать
            // имя до того, как заведена первая бумага, — лишний шаг перед
            // пустым экраном.
            <div className="py-8 text-center">
              <p className="text-sm text-text-muted">{t("investments.noPortfolios")}</p>
              <Button
                className="mt-3"
                onClick={() => createPortfolio.mutate({ name: t("investments.defaultPortfolio") })}
                disabled={createPortfolio.isPending}
              >
                <Plus size={16} />
                {t("investments.createPortfolio")}
              </Button>
            </div>
          ) : (
            <>
              <div className="flex flex-wrap gap-1">
                <FilterChip
                  label={t("investments.allPortfolios")}
                  active={portfolioId === null}
                  onClick={() => setPortfolioId(null)}
                />
                {(portfolios ?? []).map((portfolio) => (
                  <FilterChip
                    key={portfolio.id}
                    label={portfolio.name}
                    active={portfolioId === portfolio.id}
                    onClick={() => setPortfolioId(portfolio.id)}
                  />
                ))}
                {/* Правка — у выбранного портфеля, а не у каждого: значок
                    на каждой метке превратил бы ряд в частокол кнопок.
                    При «Все» править нечего, и кнопка не показывается. */}
                {portfolioId !== null && (
                  <button
                    type="button"
                    aria-label={t("investments.editPortfolio")}
                    title={t("investments.editPortfolio")}
                    onClick={() => {
                      setEditingPortfolio(
                        (portfolios ?? []).find((item) => item.id === portfolioId) ?? null
                      );
                      setPortfolioModalOpen(true);
                    }}
                    className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
                  >
                    <Pencil size={14} />
                  </button>
                )}
                <button
                  type="button"
                  aria-label={t("investments.newPortfolio")}
                  title={t("investments.newPortfolio")}
                  onClick={() => {
                    setEditingPortfolio(null);
                    setPortfolioModalOpen(true);
                  }}
                  className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
                >
                  <Plus size={14} />
                </button>
              </div>

              <div className="flex flex-wrap gap-1">
                {KINDS.map((item) => (
                  <FilterChip
                    key={item}
                    label={t(`investments.kind.${item}` as never)}
                    active={kind === item}
                    onClick={() => setKind(item)}
                  />
                ))}
              </div>

              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                <Stat label={t("investments.value")} value={formatCurrency(totals.value)} />
                <Stat label={t("investments.costBasis")} value={formatCurrency(totals.cost)} />
                <Stat
                  label={t("investments.realised")}
                  value={formatSignedCurrency(totals.realised)}
                  tone={totals.realised > 0 ? "success" : totals.realised < 0 ? "danger" : undefined}
                />
              </div>
              {totals.unpriced > 0 && (
                <p className="text-xs text-text-muted">
                  {t("investments.unpricedHint", { count: totals.unpriced })}
                </p>
              )}

              {isLoading ? (
                <p className="py-10 text-center text-sm text-text-muted">{t("common.loading")}</p>
              ) : (
                <HoldingList items={visible} onOpen={(holding) => setDetailId(holding.id)} />
              )}
            </>
          )}
        </CardContent>
      </Card>

      <PortfolioFormModal
        open={portfolioModalOpen}
        onClose={() => setPortfolioModalOpen(false)}
        portfolio={editingPortfolio}
        // Удалённый портфель перестаёт существовать вместе с выбором:
        // оставить его выбранным значило бы показывать пустой список
        // бумаг без объяснения, куда они делись.
        onDeleted={() => setPortfolioId(null)}
      />

      <HoldingFormModal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        portfolios={portfolios ?? []}
        defaultPortfolioId={portfolioId}
      />
      <HoldingDetailModal holdingId={detailId} onClose={() => setDetailId(null)} />
    </div>
  );
}

function FilterChip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-md px-2.5 py-1 text-xs font-medium ${
        active ? "bg-surface-2 text-text-primary" : "text-text-muted hover:bg-surface-2 hover:text-text-primary"
      }`}
    >
      {label}
    </button>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: "success" | "danger" }) {
  const color = tone === "success" ? "text-success" : tone === "danger" ? "text-danger" : "text-text-primary";
  return (
    <div className="rounded-lg border border-border p-3">
      <p className="text-xs text-text-muted">{label}</p>
      <p className={`mt-0.5 text-lg font-semibold tabular-nums ${color}`}>{value}</p>
    </div>
  );
}
