import { useMemo, useState } from "react";
import { Plus } from "lucide-react";
import { PageActions } from "@/components/layout/PageActions";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { TransitByPersonCard } from "@/components/debts/TransitByPersonCard";
import { SettlementTable } from "@/components/debts/SettlementTable";
import { CreditList } from "@/components/debts/CreditList";
import { CreditCalculator } from "@/components/debts/CreditCalculator";
import { CreditTermsModal } from "@/components/debts/CreditTermsModal";
import { PillSelector } from "@/components/layout/PillSelector";
import { useAccounts } from "@/hooks/useAccounts";
import {
  useCredits,
  useCreditSummary,
  useSettlements,
  useSettlementSummary,
  useTransitByPerson,
  useTransitSummary,
} from "@/hooks/useDebts";
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
  const { data: transit } = useTransitSummary();
  // За всё время: колонка в таблице людей отвечает на вопрос «сошлось ли с
  // ним вообще». Разрез по месяцам — в карточке внизу, у неё свой фильтр.
  const { data: transitByPerson } = useTransitByPerson();
  const { data: credits, isLoading: creditsLoading } = useCredits();
  const { data: creditSummary } = useCreditSummary();
  const { data: accounts } = useAccounts(false);

  const [modalOpen, setModalOpen] = useState(false);
  const [editingTerms, setEditingTerms] = useState<CreditTerms | null>(null);
  // Калькулятор вкладкой, а не карточкой в общей ленте: он отвечает на
  // вопрос «брать или не брать», который задают до того, как долг
  // появился, и мешать его с картиной уже случившихся долгов не стоит.
  const [view, setView] = useState<"debts" | "calculator">("debts");

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

  const viewOptions: Array<{ value: "debts" | "calculator"; label: string }> = [
    { value: "debts", label: t("debts.viewDebts") },
    { value: "calculator", label: t("credit.calculatorTab") },
  ];

  if (view === "calculator") {
    return (
      <div className="space-y-5">
        <PillSelector options={viewOptions} value={view} onChange={setView} />
        <CreditCalculator />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <PillSelector options={viewOptions} value={view} onChange={setView} />

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

      {/* Транзит стоит отдельно от долгов, а не рядом с ними в таблице
          людей: между мной и человеком, через которого прошли деньги, не
          произошло ничего, и строка в расчётах читалась бы как щедрость
          одного и просьба другого. Но чужая тысяча, лежащая на карте, —
          реальные деньги, которые нельзя тратить.

          Карточка появляется только когда транзиты вообще были: у
          большинства их нет, и пустая строка объясняла бы понятие, которым
          человек не пользуется. */}
      {transit && (Number(transit.passed_through) !== 0 || Number(transit.held) !== 0) && (
        <div className="grid gap-3 sm:grid-cols-2">
          <SummaryCard
            label={t("debts.transitPassed")}
            value={transit.passed_through}
            tone="neutral"
          />
          <SummaryCard
            label={t("debts.transitHeld")}
            value={transit.held}
            tone="neutral"
            // Минус означает «передал вперёд из своих»: не ошибка, но и не
            // то же самое, что чужие деньги на счёте.
            hint={Number(transit.held) < 0 ? t("debts.transitAdvancedHint") : t("debts.transitHeldHint")}
          />
        </div>
      )}

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
              <SettlementTable items={settlements ?? []} transit={transitByPerson} />
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

      {/* Транзит по людям — в самом конце: у большинства транзитов нет
          вовсе, а долги и кредиты есть почти у всех. */}
      <TransitByPersonCard />
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
  tone: "positive" | "negative" | "neutral";
  hint?: string;
}) {
  // Ноль не красится: красный ноль читается как проблема, которой нет.
  // Транзит не красится вовсе: это не прибыль и не потеря, а чужие деньги,
  // и любой цвет здесь означал бы оценку, которой у них нет.
  const isZero = Number(value) === 0;
  const color =
    isZero || tone === "neutral"
      ? "text-text-secondary"
      : tone === "positive"
        ? "text-success"
        : "text-danger";

  return (
    <div className="rounded-lg border border-border bg-surface-1 p-4">
      <p className="text-xs text-text-muted">{label}</p>
      <p className={`mt-1 text-xl font-semibold tabular-nums ${color}`}>{formatCurrency(value)}</p>
      {hint && <p className="mt-1 text-xs text-text-muted">{hint}</p>}
    </div>
  );
}
