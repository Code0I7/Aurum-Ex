import { useMemo, useState } from "react";
import { Plus } from "lucide-react";
import { PageActions } from "@/components/layout/PageActions";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { SettlementTable } from "@/components/debts/SettlementTable";
import { CreditList } from "@/components/debts/CreditList";
import { CreditTermsModal } from "@/components/debts/CreditTermsModal";
import { useAccounts } from "@/hooks/useAccounts";
import { useCredits, useCreditSummary, useSettlements, useSettlementSummary } from "@/hooks/useDebts";
import { HelpBadge } from "@/components/ui/HelpBadge";
import { useTranslation } from "@/lib/i18n";
import { formatCurrency } from "@/lib/format";
import type { CreditTerms } from "@/types";

/**
 * Долги — люди и банки на одной странице, но в разных блоках.
 *
 * Общего у них только знак: и там, и там деньги не ваши. Всё остальное
 * различается — у человека есть оборот и нет ставки, у банка наоборот, — и
 * сводить их в одну таблицу значило бы половину колонок оставить пустыми.
 *
 * Отдельный раздел, а не вкладка внутри счетов: контрагент с большим
 * отрицательным оборотом не дыра в бюджете, а человек, который много вам
 * передавал.
 */
export function DebtsPage() {
  const { t } = useTranslation();
  const { data: settlements, isLoading: settlementsLoading } = useSettlements();
  const { data: settlementSummary } = useSettlementSummary();
  const { data: credits, isLoading: creditsLoading } = useCredits();
  const { data: creditSummary } = useCreditSummary();
  const { data: accounts } = useAccounts(false);

  const [modalOpen, setModalOpen] = useState(false);
  const [editingTerms, setEditingTerms] = useState<CreditTerms | null>(null);

  // Кандидаты на заведение условий — счета-обязательства, у которых условий
  // ещё нет. Счёт с условиями в список не попадает: его правят карандашом на
  // карточке, а не заводят второй раз.
  const candidates = useMemo(() => {
    const taken = new Set((credits ?? []).map((item) => item.account_id));
    return (accounts ?? []).filter(
      (account) => account.nature === "liability" && !taken.has(account.id),
    );
  }, [accounts, credits]);

  function openCreate() {
    setEditingTerms(null);
    setModalOpen(true);
  }

  function openEdit(item: CreditTerms) {
    setEditingTerms(item);
    setModalOpen(true);
  }

  return (
    <div className="space-y-5">
      {/* Три числа сверху: сколько должны вам, сколько должны вы людям,
          сколько банкам. Долг банку и долг брату разделены намеренно —
          у первого есть ставка, и он растёт сам. */}
      <div className="grid gap-3 sm:grid-cols-3">
        <SummaryCard
          label={t("debts.owedToMe")}
          value={settlementSummary?.owed_to_me ?? "0"}
          tone="positive"
        />
        <SummaryCard
          label={t("debts.owedByMe")}
          value={settlementSummary?.owed_by_me ?? "0"}
          tone="negative"
        />
        <SummaryCard
          label={t("debts.creditsTotal")}
          value={creditSummary?.debt ?? "0"}
          tone="negative"
          hint={
            creditSummary && Number(creditSummary.estimated_monthly_interest) > 0
              ? `≈ ${formatCurrency(creditSummary.estimated_monthly_interest)} / ${t("debts.monthlyInterest").toLowerCase()}`
              : undefined
          }
        />
      </div>

      {/* Кредиты выше расчётов с людьми: их статистически единицы, а
          строк с людьми — десятки, и короткий список не должен ждать
          конца длинного. */}
      <Card>
        <CardHeader>
          <CardTitle>{t("debts.credits")}</CardTitle>
          <PageActions>
            <Button onClick={openCreate} disabled={candidates.length === 0}>
              <Plus size={16} />
              {t("debts.addCredit")}
            </Button>
          </PageActions>
        </CardHeader>
        <CardContent>
          {creditsLoading ? (
            <p className="py-10 text-center text-sm text-text-muted">{t("common.loading")}</p>
          ) : (
            <CreditList items={credits ?? []} onEdit={openEdit} />
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-1.5">
            {t("debts.people")}
            <HelpBadge hintKey="help.settlements" />
          </CardTitle>
        </CardHeader>
        <CardContent>
          {settlementsLoading ? (
            <p className="py-10 text-center text-sm text-text-muted">{t("common.loading")}</p>
          ) : (
            <>
              <SettlementTable items={settlements ?? []} />
              {(settlements?.length ?? 0) > 0 && (
                <p className="mt-3 text-xs text-text-muted">{t("debts.turnoverHint")}</p>
              )}
            </>
          )}
        </CardContent>
      </Card>

      <CreditTermsModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        terms={editingTerms}
        candidates={candidates}
      />
    </div>
  );
}

function SummaryCard({
  label,
  value,
  tone,
  hint,
}: {
  label: string;
  value: string;
  tone: "positive" | "negative";
  hint?: string;
}) {
  // Ноль не красится: красный ноль читается как проблема, которой нет.
  const isZero = Number(value) === 0;
  const color = isZero ? "text-text-secondary" : tone === "positive" ? "text-success" : "text-danger";

  return (
    <div className="rounded-lg border border-border bg-surface-1 p-4">
      <p className="text-xs text-text-muted">{label}</p>
      <p className={`mt-1 text-xl font-semibold tabular-nums ${color}`}>{formatCurrency(value)}</p>
      {hint && <p className="mt-1 text-xs text-text-muted">{hint}</p>}
    </div>
  );
}
