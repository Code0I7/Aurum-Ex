import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { HelpBadge } from "@/components/ui/HelpBadge";
import { Input, Label } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { formatCurrency } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import { annualFromMonthly } from "@/lib/roi";
import { cn } from "@/lib/utils";

export type RateMode = "amount" | "annual" | "monthly";

export interface RoiForm {
  initial: string;
  /** Ожидаемая выплата в месяц — для режима ввода суммой. */
  monthlyPayout: string;
  /** Ставка выплат: годовая или месячная, смотря какой режим. */
  payoutRate: string;
  growthRate: string;
  contribution: string;
  contributionIndex: string;
  reinvest: boolean;
  years: string;
}

interface Props {
  form: RoiForm;
  onChange: (patch: Partial<RoiForm>) => void;
  mode: RateMode;
  onModeChange: (mode: RateMode) => void;
  /** Итоговая годовая ставка выплат — показывается под полем, чтобы было
   * видно, во что превращается введённое. */
  resolvedAnnualPercent: number | null;
}

/**
 * Ввод для калькулятора доходности.
 *
 * Три способа задать доходность, потому что люди думают о ней по-разному:
 * «квартира приносит 30 тысяч в месяц», «вклад под 18 % годовых», «ставка
 * 1,5 % в месяц». Считать одно из другого в уме неудобно, поэтому режим
 * выбирается, а рядом всегда показано, во что введённое превращается в
 * годовых.
 *
 * Ставки переводятся друг в друга через корень двенадцатой степени, а не
 * делением на 12: месячная ставка, начисленная двенадцать раз, даёт за год
 * больше заявленного, и деление незаметно завышает результат.
 */
export function RoiInputsCard({ form, onChange, mode, onModeChange, resolvedAnnualPercent }: Props) {
  const { t } = useTranslation();

  const monthlyHint =
    mode === "monthly" && form.payoutRate !== ""
      ? t("roi.monthlyRateHint", { annual: annualFromMonthly(Number(form.payoutRate)).toFixed(1) })
      : null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("roi.title")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <Label htmlFor="roi-initial">{t("roi.initialLabel")}</Label>
          <Input
            id="roi-initial"
            type="number"
            inputMode="decimal"
            min="0"
            value={form.initial}
            onChange={(event) => onChange({ initial: event.target.value })}
            placeholder="500000"
          />
        </div>

        <div>
          <span className="mb-1.5 block text-xs font-medium text-text-secondary">{t("roi.modeLabel")}</span>
          <div className="flex flex-wrap gap-2">
            {(["amount", "annual", "monthly"] as RateMode[]).map((value) => (
              <Button
                key={value}
                type="button"
                variant={mode === value ? "primary" : "secondary"}
                onClick={() => onModeChange(value)}
                className="whitespace-nowrap"
              >
                {t(`roi.mode.${value}` as "roi.mode.amount")}
              </Button>
            ))}
          </div>
        </div>

        {mode === "amount" ? (
          <div>
            <Label htmlFor="roi-monthly">{t("roi.monthlyPayoutLabel")}</Label>
            <Input
              id="roi-monthly"
              type="number"
              inputMode="decimal"
              min="0"
              value={form.monthlyPayout}
              onChange={(event) => onChange({ monthlyPayout: event.target.value })}
              placeholder="8000"
            />
          </div>
        ) : (
          <div>
            <Label htmlFor="roi-rate">
              {mode === "annual" ? t("roi.annualRateLabel") : t("roi.monthlyRateLabel")}
            </Label>
            <Input
              id="roi-rate"
              type="number"
              inputMode="decimal"
              step="0.1"
              value={form.payoutRate}
              onChange={(event) => onChange({ payoutRate: event.target.value })}
              placeholder={mode === "annual" ? "18" : "1.5"}
            />
            {monthlyHint && <p className="mt-1 text-xs text-text-muted">{monthlyHint}</p>}
          </div>
        )}

        <div>
          {/* Объяснение поля — в подсказке у названия, а не строкой под
              ним. Поля тут понятные, и абзац под каждым читается один раз,
              а место занимает всегда. */}
          <Label htmlFor="roi-growth" className="flex items-center gap-1.5">
            {t("roi.growthLabel")}
            <HelpBadge hintKey="roi.growthHint" />
          </Label>
          <Input
            id="roi-growth"
            type="number"
            inputMode="decimal"
            step="0.1"
            value={form.growthRate}
            onChange={(event) => onChange({ growthRate: event.target.value })}
            placeholder="0"
          />
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <Label htmlFor="roi-contribution" className="flex items-center gap-1.5">
              {t("roi.contributionLabel")}
              <HelpBadge hintKey="roi.contributionHint" />
            </Label>
            <Input
              id="roi-contribution"
              type="number"
              inputMode="decimal"
              min="0"
              value={form.contribution}
              onChange={(event) => onChange({ contribution: event.target.value })}
              placeholder="0"
            />
          </div>
          <div>
            <Label htmlFor="roi-index">{t("roi.contributionIndexLabel")}</Label>
            <Input
              id="roi-index"
              type="number"
              inputMode="decimal"
              step="0.5"
              value={form.contributionIndex}
              onChange={(event) => onChange({ contributionIndex: event.target.value })}
              placeholder="0"
            />
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <Label htmlFor="roi-years">{t("roi.yearsLabel")}</Label>
            <Input
              id="roi-years"
              type="number"
              inputMode="numeric"
              min="1"
              max="50"
              value={form.years}
              onChange={(event) => onChange({ years: event.target.value })}
            />
          </div>
          <label className="flex items-end gap-2 pb-2 text-sm text-text-primary">
            <input
              type="checkbox"
              checked={form.reinvest}
              onChange={(event) => onChange({ reinvest: event.target.checked })}
              className="h-4 w-4 accent-text-primary"
            />
            <span>
              {t("roi.reinvestLabel")}
              <HelpBadge hintKey="roi.reinvestHint" />
            </span>
          </label>
        </div>

        {resolvedAnnualPercent !== null && (
          <p className={cn("text-sm text-text-muted")}>
            {t("roi.resolvedRate", { percent: resolvedAnnualPercent.toFixed(1) })}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

/** Одна строка итога — вынесена, чтобы карточки результатов выглядели
 * одинаково и не расходились по мере правок. */
export function ResultRow({ label, value, hint, tone }: { label: string; value: number; hint?: string; tone?: "good" | "muted" }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-gridline py-2 last:border-b-0">
      <span className="text-sm text-text-muted">
        {label}
        {hint && <span className="block text-xs text-text-muted/70">{hint}</span>}
      </span>
      <span
        className={cn(
          "shrink-0 tabular-nums font-medium",
          tone === "good" ? "text-success" : tone === "muted" ? "text-text-muted" : "text-text-primary"
        )}
      >
        {formatCurrency(value)}
      </span>
    </div>
  );
}
