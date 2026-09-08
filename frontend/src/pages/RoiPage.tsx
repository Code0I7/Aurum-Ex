import { useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { ResultRow, RoiInputsCard, type RateMode, type RoiForm } from "@/components/roi/RoiInputsCard";
import { RoiProjectionCard } from "@/components/roi/RoiProjectionCard";
import { useTranslation } from "@/lib/i18n";
import { annualFromMonthly, calculateRoi, monthlyRate } from "@/lib/roi";

const EMPTY: RoiForm = {
  initial: "",
  monthlyPayout: "",
  payoutRate: "",
  growthRate: "",
  contribution: "",
  contributionIndex: "",
  reinvest: true,
  years: "10",
};

/**
 * Калькулятор доходности вложения.
 *
 * Считает по месяцам: деньги, отложенные в марте, к декабрю успевают
 * поработать девять месяцев, и годовой шаг эту разницу теряет. Довложение
 * вносится в конце месяца — работать начинает со следующего, как и бывает,
 * когда откладываешь с зарплаты.
 *
 * Ничего не сохраняет и ни с чем в приложении не связан: это черновик,
 * которым прикидывают покупку до того, как она случилась.
 */
export function RoiPage() {
  const { t } = useTranslation();
  const [form, setForm] = useState<RoiForm>(EMPTY);
  const [mode, setMode] = useState<RateMode>("amount");

  const patch = (next: Partial<RoiForm>) => setForm((prev) => ({ ...prev, ...next }));

  const initial = Number(form.initial) || 0;

  // Месячная ставка выплат — к ней сводятся все три способа ввода.
  // Месячная, а не годовая: введённые «5 000 в месяц» должны и в первый
  // месяц дать ровно 5 000, иначе человек вводит одно, а видит другое.
  const payoutMonthlyRate = useMemo(() => {
    if (mode === "annual") return monthlyRate(Number(form.payoutRate) || 0);
    if (mode === "monthly") return (Number(form.payoutRate) || 0) / 100;
    if (initial <= 0) return 0;
    return (Number(form.monthlyPayout) || 0) / initial;
  }, [mode, form.payoutRate, form.monthlyPayout, initial]);

  const hasInput = initial > 0 && (payoutMonthlyRate > 0 || Number(form.growthRate) > 0);

  const result = useMemo(() => {
    if (!hasInput) return null;
    return calculateRoi({
      initial,
      payoutMonthlyRate,
      growthRatePercent: Number(form.growthRate) || 0,
      monthlyContribution: Number(form.contribution) || 0,
      contributionIndexPercent: Number(form.contributionIndex) || 0,
      reinvestPayouts: form.reinvest,
      // Горизонт зажат в разумные пределы: на 200 годах проекция
      // превращается в бессмыслицу, а таблица — в километр строк.
      years: Math.min(50, Math.max(1, Number(form.years) || 10)),
    });
  }, [hasInput, initial, payoutMonthlyRate, form]);

  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <RoiInputsCard
        form={form}
        onChange={patch}
        mode={mode}
        onModeChange={setMode}
        resolvedAnnualPercent={hasInput ? annualFromMonthly(payoutMonthlyRate * 100) : null}
      />

      {result ? (
        <Card>
          <CardHeader>
            <CardTitle>{t("roi.resultTitle")}</CardTitle>
          </CardHeader>
          <CardContent>
            <ResultRow
              label={t("roi.firstMonthPayout")}
              value={result.firstMonthPayout}
              hint={t("roi.firstMonthHint")}
            />
            <ResultRow
              label={t("roi.contributedTotal")}
              value={result.contributed}
              hint={t("roi.contributedHint")}
              tone="muted"
            />
            <ResultRow label={t("roi.earnedTotal")} value={result.earned} hint={t("roi.earnedHint")} tone="good" />
            <ResultRow label={t("roi.finalTotal")} value={result.total} />

            <p className="mt-3 text-sm text-text-muted">
              {result.paybackYears !== null
                ? t("roi.payback", { years: result.paybackYears.toFixed(1) })
                : t("roi.noPayback")}
            </p>
          </CardContent>
        </Card>
      ) : (
        // Пустая карточка тянется на всю высоту соседней с формой, а
        // подсказка стоит по центру: прижатая к верху, она висела в
        // воздухе напротив середины формы.
        <Card className="flex">
          <CardContent className="flex flex-1 items-center justify-center p-8 text-center text-sm text-text-muted">
            {t("roi.emptyHint")}
          </CardContent>
        </Card>
      )}

      {result && (
        <div className="lg:col-span-2">
          <RoiProjectionCard rows={result.years} />
        </div>
      )}
    </div>
  );
}
