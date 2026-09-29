import { useEffect, useState } from "react";
import { Plus, X } from "lucide-react";
import { Combobox } from "@/components/ui/Combobox";
import { Dialog } from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { Input, Label, Textarea } from "@/components/ui/Input";
import { useDeleteCreditTerms, useSaveCreditTerms } from "@/hooks/useDebts";
import { useTranslation } from "@/lib/i18n";
import { useConfirm } from "@/components/ui/ConfirmProvider";
import type { AccountWithBalance, CreditRateInput, CreditTerms } from "@/types";

interface CreditTermsModalProps {
  open: boolean;
  onClose: () => void;
  /** Условия, которые правим. null — заводим новые для выбранного счёта. */
  terms?: CreditTerms | null;
  /** Счета-обязательства без условий — только для режима создания. */
  candidates: AccountWithBalance[];
}

const EMPTY_FORM = {
  annual_rate_percent: "",
  credit_limit: "",
  grace_days: "",
  payment_day: "",
  minimum_payment: "",
  minimum_payment_percent: "",
  closes_on: "",
  notes: "",
};

interface RateRow {
  name: string;
  percent: string;
  condition: string;
}

/**
 * Число из поля, введённого человеком.
 *
 * «24,9» и «127 000» — это то, как числа написаны в договоре и как их и
 * набирают. Сервер ждёт «24.9» и «127000», и без этой замены сохранение
 * молча отвечало 422, а форма показывала «не удалось сохранить», не
 * объясняя, что именно ему не понравилось.
 *
 * Пустая строка означает «не задано», а не ноль: нулевая ставка — это
 * беспроцентная рассрочка, вполне осмысленное значение.
 */
function decimalOrNull(value: string): string | null {
  const cleaned = value.replace(/[\s ]/g, "").replace(",", ".").trim();
  return cleaned === "" ? null : cleaned;
}

function intOrNull(value: string): number | null {
  const cleaned = value.replace(/[\s ]/g, "").trim();
  return cleaned === "" ? null : Number(cleaned);
}

/**
 * Условия по кредиту.
 *
 * Все поля необязательны, и это осознанно: у беспроцентной рассрочки нет
 * ставки, у обычного кредита нет лимита. Требовать заполнить всё значило бы
 * заставить придумывать числа, а придуманное число хуже пустого.
 */
export function CreditTermsModal({ open, onClose, terms, candidates }: CreditTermsModalProps) {
  const { t } = useTranslation();
  const saveTerms = useSaveCreditTerms();
  const removeTerms = useDeleteCreditTerms();
  const confirm = useConfirm();

  const [accountId, setAccountId] = useState<number | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [rates, setRates] = useState<RateRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  // Число месяца вне 1–28: сохранять такое незачем, но и стирать введённое
  // за человека нельзя — поэтому предупреждение и заблокированная кнопка.
  const day = Number(form.payment_day);
  const dayError = form.payment_day.trim() !== "" && (!Number.isInteger(day) || day < 1 || day > 28);

  useEffect(() => {
    if (!open) return;
    setError(null);
    if (terms) {
      setAccountId(terms.account_id);
      setForm({
        annual_rate_percent: terms.annual_rate_percent ?? "",
        credit_limit: terms.credit_limit ?? "",
        grace_days: terms.grace_days?.toString() ?? "",
        payment_day: terms.payment_day?.toString() ?? "",
        minimum_payment: terms.minimum_payment ?? "",
        minimum_payment_percent: terms.minimum_payment_percent ?? "",
        closes_on: terms.closes_on ?? "",
        notes: terms.notes ?? "",
      });
      setRates(
        terms.rates.map((rate) => ({
          name: rate.name,
          percent: rate.percent,
          condition: rate.condition ?? "",
        }))
      );
    } else {
      setAccountId(candidates[0]?.id ?? null);
      setForm(EMPTY_FORM);
      setRates([]);
    }
  }, [open, terms, candidates]);

  function updateRate(index: number, patch: Partial<RateRow>) {
    setRates((prev) => prev.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (accountId === null) return;
    setError(null);

    // Строка без названия или без процента — это незаполненная строка, а не
    // ставка «ноль без имени»: такие просто не уезжают на сервер.
    const filledRates: CreditRateInput[] = rates
      .filter((row) => row.name.trim() !== "" && decimalOrNull(row.percent) !== null)
      .map((row) => ({
        name: row.name.trim(),
        percent: decimalOrNull(row.percent) as string,
        condition: row.condition.trim() === "" ? null : row.condition.trim(),
      }));

    try {
      await saveTerms.mutateAsync({
        accountId,
        input: {
          annual_rate_percent: decimalOrNull(form.annual_rate_percent),
          credit_limit: decimalOrNull(form.credit_limit),
          grace_days: intOrNull(form.grace_days),
          payment_day: intOrNull(form.payment_day),
          minimum_payment: decimalOrNull(form.minimum_payment),
          minimum_payment_percent: decimalOrNull(form.minimum_payment_percent),
          closes_on: form.closes_on.trim() === "" ? null : form.closes_on,
          notes: form.notes.trim() === "" ? null : form.notes,
          rates: filledRates,
        },
      });
      onClose();
    } catch (err) {
      // Текст сервера, а не общая фраза: 422 говорит, какое поле ему не
      // понравилось, и прятать это значит оставить человека гадать.
      setError(err instanceof Error ? err.message : t("debts.saveError"));
    }
  }

  async function handleRemove() {
    if (!terms) return;
    const ok = await confirm({
      message: t("debts.confirmRemoveTerms", { name: terms.account_name }),
      confirmLabel: t("common.delete"),
      tone: "danger",
    });
    if (!ok) return;
    await removeTerms.mutateAsync(terms.account_id);
    onClose();
  }

  const title = terms ? t("debts.termsFor", { name: terms.account_name }) : t("debts.addCredit");
  const isSaving = saveTerms.isPending || removeTerms.isPending;

  return (
    <Dialog open={open} onClose={onClose} title={title}>
      <form onSubmit={handleSubmit} className="space-y-3">
        {/* Счёт выбирается только при заведении: перевесить готовые условия
            на другой счёт — не правка, а новая запись. */}
        {!terms && (
          <div>
            <Label htmlFor="credit-account">{t("debts.pickAccount")}</Label>
            {candidates.length === 0 ? (
              <p className="mt-1 text-xs text-text-muted">{t("debts.noLiabilityAccounts")}</p>
            ) : (
              <Combobox
                id="credit-account"
                className="mt-1"
                options={candidates.map((account) => ({ value: String(account.id), label: account.name }))}
                value={accountId ? String(accountId) : ""}
                onChange={(value) => setAccountId(Number(value))}
                placeholder={t("debts.pickAccount")}
              />
            )}
          </div>
        )}

        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <Label htmlFor="credit-rate">{t("debts.rate")}, %</Label>
            <Input
              id="credit-rate"
              inputMode="decimal"
              value={form.annual_rate_percent}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, annual_rate_percent: event.target.value }))
              }
            />
            <p className="mt-1 text-xs text-text-muted">{t("debts.rateHint")}</p>
          </div>
          <div>
            <Label htmlFor="credit-limit">{t("debts.limit")}</Label>
            <Input
              id="credit-limit"
              inputMode="decimal"
              value={form.credit_limit}
              onChange={(event) => setForm((prev) => ({ ...prev, credit_limit: event.target.value }))}
            />
          </div>
          <div>
            <Label htmlFor="credit-grace">{t("debts.gracePeriod")}</Label>
            <Input
              id="credit-grace"
              inputMode="numeric"
              value={form.grace_days}
              onChange={(event) => setForm((prev) => ({ ...prev, grace_days: event.target.value }))}
            />
          </div>
          <div>
            <Label htmlFor="credit-day">{t("debts.paymentDay")}</Label>
            {/* Обычное поле, а не счётчик: стрелочки «плюс один» до
                двадцать пятого никто нажимать не станет. Ограничение
                1–28 — потому что двадцать девятого, тридцатого и
                тридцать первого есть не в каждом месяце. */}
            <Input
              id="credit-day"
              inputMode="numeric"
              value={form.payment_day}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, payment_day: event.target.value.replace(/[^0-9]/g, "") }))
              }
            />
            {dayError && <p className="mt-1 text-xs text-danger">{t("debts.paymentDayRange")}</p>}
          </div>
          {/* Минимальный платёж двумя полями: банк задаёт его правилом —
              «не более 8% от задолженности, минимум 600 рублей», — и одно
              фиксированное число устаревает в первый же месяц. */}
          <div>
            <Label htmlFor="credit-minimum-percent">{t("debts.minimumPercent")}</Label>
            <Input
              id="credit-minimum-percent"
              inputMode="decimal"
              value={form.minimum_payment_percent}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, minimum_payment_percent: event.target.value }))
              }
            />
          </div>
          <div>
            <Label htmlFor="credit-minimum">{t("debts.minimumFloor")}</Label>
            <Input
              id="credit-minimum"
              inputMode="decimal"
              value={form.minimum_payment}
              onChange={(event) => setForm((prev) => ({ ...prev, minimum_payment: event.target.value }))}
            />
          </div>
          <div className="sm:col-span-2">
            <Label htmlFor="credit-closes">{t("debts.closesOn")}</Label>
            <Input
              id="credit-closes"
              type="date"
              value={form.closes_on}
              onChange={(event) => setForm((prev) => ({ ...prev, closes_on: event.target.value }))}
            />
          </div>
        </div>

        {/* Матрица ставок: в тарифе карты их семь, и одна строка «ставка»
            заставляла выбирать из них одну и забывать остальные ровно
            тогда, когда они понадобятся. */}
        <div className="rounded-lg border border-border p-3">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
              {t("debts.rateMatrix")}
            </p>
            <button
              type="button"
              onClick={() => setRates((prev) => [...prev, { name: "", percent: "", condition: "" }])}
              className="flex items-center gap-1 text-xs text-text-muted hover:text-text-primary"
            >
              <Plus size={14} />
              {t("debts.addRate")}
            </button>
          </div>
          <p className="mt-1 text-xs text-text-muted">{t("debts.rateMatrixHint")}</p>

          {rates.length > 0 && (
            <ul className="mt-2 space-y-2">
              {rates.map((row, index) => (
                <li key={index} className="grid grid-cols-[1fr_5rem_1fr_auto] items-center gap-2">
                  <Input
                    aria-label={t("debts.rateName")}
                    placeholder={t("debts.rateName")}
                    value={row.name}
                    onChange={(event) => updateRate(index, { name: event.target.value })}
                  />
                  <Input
                    aria-label={t("debts.rate")}
                    inputMode="decimal"
                    value={row.percent}
                    onChange={(event) => updateRate(index, { percent: event.target.value })}
                  />
                  <Input
                    aria-label={t("debts.rateCondition")}
                    placeholder={t("debts.rateCondition")}
                    value={row.condition}
                    onChange={(event) => updateRate(index, { condition: event.target.value })}
                  />
                  <button
                    type="button"
                    aria-label={t("common.delete")}
                    onClick={() => setRates((prev) => prev.filter((_, i) => i !== index))}
                    className="rounded-md p-1.5 text-text-muted hover:text-danger"
                  >
                    <X size={14} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div>
          <Label htmlFor="credit-notes">{t("debts.notes")}</Label>
          {/* Многострочное поле: сюда переезжает всё, чего в модели нет, —
              платы за обслуживание и снятие, бесплатные лимиты переводов,
              неустойка. В одну строку это не помещалось. */}
          <Textarea
            id="credit-notes"
            rows={4}
            value={form.notes}
            onChange={(event) => setForm((prev) => ({ ...prev, notes: event.target.value }))}
          />
        </div>

        <p className="text-xs text-text-muted">{t("debts.monthlyInterestHint")}</p>

        {error && <p className="text-sm text-danger">{error}</p>}

        <div className="flex items-center justify-between gap-2 pt-1">
          {terms ? (
            <button
              type="button"
              onClick={handleRemove}
              className="text-xs text-text-muted hover:text-danger"
            >
              {t("debts.removeTerms")}
            </button>
          ) : (
            <span />
          )}
          <div className="flex gap-2">
            <Button type="button" variant="secondary" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={isSaving || accountId === null || dayError}>
              {t("common.save")}
            </Button>
          </div>
        </div>
      </form>
    </Dialog>
  );
}
