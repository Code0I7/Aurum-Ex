import { useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Label, Select } from "@/components/ui/Input";
import { HelpBadge } from "@/components/ui/HelpBadge";
import { useCreditPlan, useCredits } from "@/hooks/useDebts";
import { useTranslation } from "@/lib/i18n";
import { formatCurrency } from "@/lib/format";
import type { CreditPlanOutcome, CreditTerms } from "@/types";

/** Число из поля: «39,9» и «40 000» — то, как их пишут и набирают. */
function decimalOrNull(value: string): string | null {
  const cleaned = value.replace(/[\s ]/g, "").replace(",", ".").trim();
  return cleaned === "" ? null : cleaned;
}

const CUSTOM = "custom";

/**
 * Калькулятор кредита.
 *
 * Отвечает на вопрос, который задают до покупки, а не после: «если взять
 * сорок тысяч и платить минимальный платёж — сколько это выйдет». В
 * приложении банка виден ежемесячный платёж и не видна переплата, а
 * решение принимается именно по ней.
 *
 * Условия подставляются из счёта, но правятся руками: посчитать хочется и
 * по карте, которой в приложении ещё нет.
 */
export function CreditCalculator() {
  const { t } = useTranslation();
  const { data: credits } = useCredits();
  const plan = useCreditPlan();

  const [accountId, setAccountId] = useState<string>(CUSTOM);
  const [amount, setAmount] = useState("");
  const [rate, setRate] = useState("");
  const [minimumPercent, setMinimumPercent] = useState("");
  const [minimumFloor, setMinimumFloor] = useState("");
  const [months, setMonths] = useState("12");
  const [fixedPayment, setFixedPayment] = useState("");
  // Плата за снятие или перевод: «2,9% плюс 290 ₽». Ложится в долг сразу,
  // и проценты идут уже на неё.
  const [feePercent, setFeePercent] = useState("");
  const [feeFixed, setFeeFixed] = useState("");

  const selected: CreditTerms | undefined = useMemo(
    () => credits?.find((item) => String(item.account_id) === accountId),
    [credits, accountId]
  );

  // Выбор счёта подставляет его условия — но только их, не сумму: сумму
  // человек вводит сам, ради неё калькулятор и открывают.
  useEffect(() => {
    if (!selected) return;
    setRate(selected.annual_rate_percent ?? "");
    setMinimumPercent(selected.minimum_payment_percent ?? "");
    setMinimumFloor(selected.minimum_payment ?? "");
  }, [selected]);

  const currency = selected?.account_currency || undefined;

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const value = decimalOrNull(amount);
    const percent = decimalOrNull(rate);
    if (!value || percent === null) return;
    plan.mutate({
      amount: value,
      annual_rate_percent: percent,
      minimum_percent: decimalOrNull(minimumPercent),
      minimum_floor: decimalOrNull(minimumFloor),
      fixed_payment: decimalOrNull(fixedPayment),
      target_months: months.trim() === "" ? null : Number(months),
      fee_percent: decimalOrNull(feePercent),
      fee_fixed: decimalOrNull(feeFixed),
    });
  }

  const result = plan.data;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <CardTitle>{t("credit.calculatorTitle")}</CardTitle>
            <HelpBadge hintKey="credit.calculatorHint" />
          </div>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <Label htmlFor="calc-account">{t("debts.pickAccount")}</Label>
              <Select
                id="calc-account"
                value={accountId}
                onChange={(event) => setAccountId(event.target.value)}
              >
                <option value={CUSTOM}>{t("credit.withoutAccount")}</option>
                {(credits ?? []).map((item) => (
                  <option key={item.account_id} value={String(item.account_id)}>
                    {item.account_name}
                  </option>
                ))}
              </Select>
            </div>

            <div className={selected && selected.rates.length > 0 ? "lg:col-span-2" : undefined}>
              <Label htmlFor="calc-rate">{t("debts.rate")}, %</Label>
              {/* Ставка выбирается из матрицы счёта, если она заведена:
                  снятие наличных и покупки стоят по-разному, и разница
                  здесь — половина ответа. Список длинный, поэтому поле
                  занимает две ячейки и идёт вторым: третьим оно не
                  помещалось бы в ряд и оставляло в нём дыру. */}
              {selected && selected.rates.length > 0 ? (
                <Select
                  id="calc-rate"
                  value={rate}
                  onChange={(event) => setRate(event.target.value)}
                >
                  {selected.annual_rate_percent && (
                    <option value={selected.annual_rate_percent}>
                      {t("credit.mainRate")} — {selected.annual_rate_percent}%
                    </option>
                  )}
                  {selected.rates.map((item) => (
                    <option key={item.id} value={item.percent}>
                      {item.name}
                      {item.condition ? ` (${item.condition})` : ""} — {item.percent}%
                    </option>
                  ))}
                </Select>
              ) : (
                <Input
                  id="calc-rate"
                  inputMode="decimal"
                  value={rate}
                  onChange={(event) => setRate(event.target.value)}
                />
              )}
            </div>

            <div>
              <Label htmlFor="calc-amount">{t("credit.amount")}</Label>
              <Input
                id="calc-amount"
                inputMode="decimal"
                autoFocus
                value={amount}
                onChange={(event) => setAmount(event.target.value)}
              />
            </div>

            <div>
              <Label htmlFor="calc-min-percent">{t("debts.minimumPercent")}</Label>
              <Input
                id="calc-min-percent"
                inputMode="decimal"
                value={minimumPercent}
                onChange={(event) => setMinimumPercent(event.target.value)}
              />
            </div>

            <div>
              <Label htmlFor="calc-min-floor">{t("debts.minimumFloor")}</Label>
              <Input
                id="calc-min-floor"
                inputMode="decimal"
                value={minimumFloor}
                onChange={(event) => setMinimumFloor(event.target.value)}
              />
            </div>

            <div>
              <Label htmlFor="calc-fee-percent">{t("credit.feePercent")}</Label>
              <Input
                id="calc-fee-percent"
                inputMode="decimal"
                value={feePercent}
                onChange={(event) => setFeePercent(event.target.value)}
              />
            </div>

            <div>
              <Label htmlFor="calc-fee-fixed">{t("credit.feeFixed")}</Label>
              <Input
                id="calc-fee-fixed"
                inputMode="decimal"
                value={feeFixed}
                onChange={(event) => setFeeFixed(event.target.value)}
              />
            </div>

            <div>
              <Label htmlFor="calc-months">{t("credit.targetMonths")}</Label>
              <Input
                id="calc-months"
                inputMode="numeric"
                value={months}
                onChange={(event) => setMonths(event.target.value)}
              />
            </div>

            <div>
              <Label htmlFor="calc-fixed">{t("credit.fixedPayment")}</Label>
              <Input
                id="calc-fixed"
                inputMode="decimal"
                placeholder={t("credit.fixedPaymentPlaceholder")}
                value={fixedPayment}
                onChange={(event) => setFixedPayment(event.target.value)}
              />
            </div>

            <div className="flex items-end">
              <Button type="submit" disabled={plan.isPending}>
                {t("credit.calculate")}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {result && Number(result.fee) > 0 && (
        <Card>
          <CardContent className="flex flex-wrap items-center gap-x-6 gap-y-1 py-4 text-sm sm:py-5">
            <span className="text-text-muted">
              {t("credit.taken")}: <span className="tabular-nums text-text-primary">{formatCurrency(amount.replace(/[\s\u00a0]/g, "").replace(",", "."), currency)}</span>
            </span>
            <span className="text-text-muted">
              {t("credit.fee")}: <span className="tabular-nums text-danger">{formatCurrency(result.fee, currency)}</span>
            </span>
            <span className="text-text-muted">
              {t("credit.debtWithFee")}:{" "}
              <span className="font-medium tabular-nums text-text-primary">
                {formatCurrency(result.amount_with_fee, currency)}
              </span>
            </span>
          </CardContent>
        </Card>
      )}

      {result && (
        <div className="grid gap-3 lg:grid-cols-3">
          <OutcomeCard
            title={t("credit.payingMinimum")}
            hint={t("credit.payingMinimumHint")}
            outcome={result.minimum}
            currency={currency}
            emptyLabel={t("credit.noMinimumRule")}
            tone="danger"
          />
          <OutcomeCard
            title={t("credit.payingRecommended", { months: months || "—" })}
            hint={t("credit.payingRecommendedHint")}
            outcome={result.recommended}
            currency={currency}
            emptyLabel={t("credit.noTargetMonths")}
            tone="neutral"
          />
          {result.fixed ? (
            <OutcomeCard
              title={t("credit.payingFixed")}
              hint={t("credit.payingFixedHint")}
              outcome={result.fixed}
              currency={currency}
              emptyLabel=""
              tone="neutral"
            />
          ) : (
            <Card>
              <CardHeader>
                <CardTitle>{t("credit.inGrace")}</CardTitle>
              </CardHeader>
              <CardContent>
                {/* Ноль процентов — не фигура речи, а строка тарифа, и
                    сравнивать переплату нужно именно с ней. */}
                <p className="text-2xl font-semibold text-success">
                  {formatCurrency(result.in_grace, currency)}
                </p>
                <p className="mt-1 text-xs text-text-muted">{t("credit.inGraceHint")}</p>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {result?.minimum && !result.minimum.never_closes && result.minimum.schedule.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>{t("credit.schedule")}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="max-h-80 overflow-y-auto">
              <table className="w-full text-sm">
                <thead className="text-xs uppercase tracking-wide text-text-muted">
                  <tr>
                    <th className="py-1.5 pr-3 text-left font-medium">{t("credit.month")}</th>
                    <th className="py-1.5 pr-3 text-right font-medium">{t("credit.payment")}</th>
                    <th className="py-1.5 pr-3 text-right font-medium">{t("credit.interestPart")}</th>
                    <th className="py-1.5 pr-3 text-right font-medium">{t("credit.principalPart")}</th>
                    <th className="py-1.5 text-right font-medium">{t("credit.balanceLeft")}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gridline">
                  {result.minimum.schedule.map((step) => (
                    <tr key={step.number}>
                      <td className="py-1.5 pr-3 text-text-muted">{step.number}</td>
                      <td className="py-1.5 pr-3 text-right tabular-nums">
                        {formatCurrency(step.payment, currency)}
                      </td>
                      <td className="py-1.5 pr-3 text-right tabular-nums text-danger">
                        {formatCurrency(step.interest, currency)}
                      </td>
                      <td className="py-1.5 pr-3 text-right tabular-nums">
                        {formatCurrency(step.principal, currency)}
                      </td>
                      <td className="py-1.5 text-right tabular-nums text-text-muted">
                        {formatCurrency(step.balance, currency)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function OutcomeCard({
  title,
  hint,
  outcome,
  currency,
  emptyLabel,
  tone,
}: {
  title: string;
  hint: string;
  outcome: CreditPlanOutcome | null;
  currency?: string;
  emptyLabel: string;
  tone: "danger" | "neutral";
}) {
  const { t } = useTranslation();

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {!outcome ? (
          <p className="text-sm text-text-muted">{emptyLabel}</p>
        ) : outcome.never_closes ? (
          // Молчать об этом нельзя: «двести лет» человек прочтёт как срок,
          // а срока здесь нет вовсе.
          <p className="text-sm text-danger">{t("credit.neverCloses")}</p>
        ) : (
          <>
            <p className="text-2xl font-semibold tabular-nums">
              {formatCurrency(outcome.first_payment, currency)}
              <span className="ml-1 text-sm font-normal text-text-muted">{t("common.perMonth")}</span>
            </p>
            <dl className="mt-3 space-y-1 text-sm">
              <Row label={t("credit.months")} value={String(outcome.months)} />
              <Row
                label={t("credit.totalPaid")}
                value={formatCurrency(outcome.total_paid, currency)}
              />
              <Row
                label={t("credit.overpaid")}
                value={formatCurrency(outcome.total_interest, currency)}
                tone={tone}
              />
            </dl>
            <p className="mt-2 text-xs text-text-muted">{hint}</p>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function Row({ label, value, tone }: { label: string; value: string; tone?: "danger" | "neutral" }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-text-muted">{label}</dt>
      <dd className={`tabular-nums ${tone === "danger" ? "font-medium text-danger" : ""}`}>{value}</dd>
    </div>
  );
}
