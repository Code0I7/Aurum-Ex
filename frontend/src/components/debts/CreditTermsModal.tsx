import { useEffect, useState } from "react";
import { Dialog } from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { Input, Label } from "@/components/ui/Input";
import { useDeleteCreditTerms, useSaveCreditTerms } from "@/hooks/useDebts";
import { useTranslation } from "@/lib/i18n";
import { useConfirm } from "@/components/ui/ConfirmProvider";
import type { AccountWithBalance, CreditTerms } from "@/types";

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
  closes_on: "",
  notes: "",
};

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
  const [error, setError] = useState<string | null>(null);

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
        closes_on: terms.closes_on ?? "",
        notes: terms.notes ?? "",
      });
    } else {
      setAccountId(candidates[0]?.id ?? null);
      setForm(EMPTY_FORM);
    }
  }, [open, terms, candidates]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (accountId === null) return;
    setError(null);

    // Пустая строка означает «не задано», а не ноль: нулевая ставка — это
    // беспроцентная рассрочка, вполне осмысленное значение, и путать её с
    // незаполненным полем нельзя.
    const optional = (value: string) => (value.trim() === "" ? null : value.trim());
    const optionalInt = (value: string) => (value.trim() === "" ? null : Number(value));

    try {
      await saveTerms.mutateAsync({
        accountId,
        input: {
          annual_rate_percent: optional(form.annual_rate_percent),
          credit_limit: optional(form.credit_limit),
          grace_days: optionalInt(form.grace_days),
          payment_day: optionalInt(form.payment_day),
          minimum_payment: optional(form.minimum_payment),
          closes_on: optional(form.closes_on),
          notes: optional(form.notes),
        },
      });
      onClose();
    } catch {
      setError(t("goal.form.saveError"));
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
              <select
                id="credit-account"
                value={accountId ?? ""}
                onChange={(event) => setAccountId(Number(event.target.value))}
                className="mt-1 w-full rounded-md border border-border bg-surface-1 px-3 py-2 text-sm"
              >
                {candidates.map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.name}
                  </option>
                ))}
              </select>
            )}
          </div>
        )}

        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <Label htmlFor="credit-rate">{t("debts.rate")}, %</Label>
            <Input
              id="credit-rate"
              inputMode="decimal"
              placeholder={t("debts.ratePlaceholder")}
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
            <Input
              id="credit-day"
              inputMode="numeric"
              min={1}
              max={31}
              type="number"
              value={form.payment_day}
              onChange={(event) => setForm((prev) => ({ ...prev, payment_day: event.target.value }))}
            />
          </div>
          <div>
            <Label htmlFor="credit-minimum">{t("debts.minimumPayment")}</Label>
            <Input
              id="credit-minimum"
              inputMode="decimal"
              value={form.minimum_payment}
              onChange={(event) => setForm((prev) => ({ ...prev, minimum_payment: event.target.value }))}
            />
          </div>
          <div>
            <Label htmlFor="credit-closes">{t("debts.closesOn")}</Label>
            <Input
              id="credit-closes"
              type="date"
              value={form.closes_on}
              onChange={(event) => setForm((prev) => ({ ...prev, closes_on: event.target.value }))}
            />
          </div>
        </div>

        <div>
          <Label htmlFor="credit-notes">{t("debts.notes")}</Label>
          <Input
            id="credit-notes"
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
            <Button type="submit" disabled={isSaving || accountId === null}>
              {t("common.save")}
            </Button>
          </div>
        </div>
      </form>
    </Dialog>
  );
}
