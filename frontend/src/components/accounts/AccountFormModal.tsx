import { useEffect, useState } from "react";
import { Dialog } from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { Input, Label, Select } from "@/components/ui/Input";
import { DirectoryPicker } from "@/components/transactions/DirectoryPicker";
import { useCreateAccount, useUpdateAccount } from "@/hooks/useAccounts";
import { useBanks, useCreateBank } from "@/hooks/useDirectories";
import { CURRENCIES, getCurrencyLabel } from "@/lib/currency";
import { useTranslation, type TranslationKey } from "@/lib/i18n";
import type { AccountKind, AccountWithBalance } from "@/types";

interface AccountFormModalProps {
  open: boolean;
  onClose: () => void;
  account?: AccountWithBalance | null;
}

const ACCOUNT_KINDS: AccountKind[] = ["checking", "savings", "credit_card", "cash", "investment", "crypto", "loan", "other"];

const EMPTY_FORM = {
  name: "",
  kind: "checking" as AccountKind,
  currency: "",
  bank_id: "",
  opening_balance: "",
  opening_date: "",
};

export function AccountFormModal({ open, onClose, account }: AccountFormModalProps) {
  const { t, language, currency } = useTranslation();
  const createAccount = useCreateAccount();
  const updateAccount = useUpdateAccount();
  const { data: banks } = useBanks();
  const createBank = useCreateBank();

  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    // У нового счёта валюта установки: карта в своей валюте — обычный
    // случай, а валютная заводится раз в несколько лет.
    setForm(
      account
        ? {
            name: account.name,
            kind: account.kind,
            currency: account.currency,
            bank_id: account.bank_id ? String(account.bank_id) : "",
            // Ноль показывается пустым полем: «ноль» и «не указано» для
            // начального остатка одно и то же.
            opening_balance:
              Number(account.opening_balance) !== 0 ? String(account.opening_balance) : "",
            opening_date: account.opening_date ?? "",
          }
        : { ...EMPTY_FORM, currency }
    );
    setError(null);
  }, [open, account]);

  const isSaving = createAccount.isPending || updateAccount.isPending;
  // Настоящая смена валюты, а не то же значение, пришедшее вместе с
  // остальными полями.
  const currencyChanged = Boolean(account) && form.currency !== account?.currency;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    // Банк уходит номером или пустотой: в состоянии формы он строкой, как
    // и любой выбор из справочника. Пустой начальный остаток — это ноль, а
    // пустая дата — «до начала учёта», и на сервере она так и хранится.
    const payload = {
      ...form,
      bank_id: form.bank_id ? Number(form.bank_id) : null,
      opening_balance: form.opening_balance.trim() === "" ? "0" : form.opening_balance,
      opening_date: form.opening_date || null,
    };

    try {
      if (account) {
        await updateAccount.mutateAsync({ id: account.id, input: payload });
      } else {
        await createAccount.mutateAsync(payload);
      }
      onClose();
    } catch {
      setError(t("account.form.saveError"));
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title={account ? t("account.form.editTitle") : t("account.form.newTitle")}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <Label htmlFor="account-name">{t("account.form.nameLabel")}</Label>
          <Input
            id="account-name"
            required
            placeholder={t("account.form.namePlaceholder")}
            value={form.name}
            onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
          />
        </div>

        {/* Валюта счёта. Менять её можно и потом: операции счёта переходят
            в новую валюту вместе с ним, а пересчёт в валюту установки
            выполняется заново по курсам на их даты.

            Предупреждение показывается только при настоящей смене, а не
            всегда: форма присылает все поля целиком, и валюта приходит в
            каждой правке — в том числе когда меняли одно название. */}
        <div>
          <Label htmlFor="account-currency">{t("account.form.currencyLabel")}</Label>
          <Select
            id="account-currency"
            value={form.currency}
            onChange={(event) => setForm((prev) => ({ ...prev, currency: event.target.value }))}
          >
            {CURRENCIES.map((option) => (
              <option key={option.code} value={option.code}>
                {getCurrencyLabel(option.code, language)}
              </option>
            ))}
          </Select>
          {account && !currencyChanged && (
            <p className="mt-1 text-xs text-text-muted">{t("account.form.currencyHint")}</p>
          )}
          {account && currencyChanged && (
            <p className="mt-1 text-xs text-danger">
              {t("account.form.currencyChangeWarning", {
                count: account.transaction_count,
                currency: form.currency,
                previous: account.currency,
                base: currency,
              })}
            </p>
          )}
        </div>

        <div>
          <Label htmlFor="account-type">{t("account.form.typeLabel")}</Label>
          <Select
            id="account-type"
            value={form.kind}
            onChange={(event) => setForm((prev) => ({ ...prev, kind: event.target.value as AccountKind }))}
          >
            {ACCOUNT_KINDS.map((type) => (
              <option key={type} value={type}>
                {t(`account.kind.${type}` as TranslationKey)}
              </option>
            ))}
          </Select>
        </div>

        {/* Начальный остаток — деньги, лежавшие на счёте до первой записи.
            Он часть остатка, но не доход: заводить его приходом значило бы
            записать заработок, которого в этот день не было.

            Поле было в базе с самого начала, но указать его было негде:
            остаток попадал в счёт только переносом таблицы, а в списке
            операций его не видно вовсе — отсюда и вопрос «откуда сразу
            5 210,40». Дата нужна, чтобы остаток встал в нужный месяц в
            движении денежных средств; пустая означает «до начала учёта». */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label htmlFor="account-opening">{t("account.form.openingBalanceLabel")}</Label>
            <Input
              id="account-opening"
              inputMode="decimal"
              placeholder="0"
              value={form.opening_balance}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, opening_balance: event.target.value }))
              }
            />
          </div>
          <div>
            <Label htmlFor="account-opening-date">{t("account.form.openingDateLabel")}</Label>
            <Input
              id="account-opening-date"
              type="date"
              value={form.opening_date}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, opening_date: event.target.value }))
              }
            />
          </div>
        </div>

        {/* Банк. Поле было в базе с самого начала, но указать его было
            негде, и отбор операций по банку оказывался пустым. Заводится
            тут же вводом названия — ходить за этим в справочник значит
            прервать заведение счёта. */}
        <div>
          <Label htmlFor="account-bank">{t("account.form.bankLabel")}</Label>
          <DirectoryPicker
            id="account-bank"
            options={banks ?? []}
            value={form.bank_id}
            onChange={(value) => setForm((prev) => ({ ...prev, bank_id: value }))}
            emptyLabel={t("account.form.noBank")}
            placeholder={t("account.form.bankPlaceholder")}
            onCreate={async (name) => (await createBank.mutateAsync({ name })).id}
          />
        </div>

        {error && <p className="text-sm text-danger">{error}</p>}

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" disabled={isSaving}>
            {isSaving ? t("common.saving") : t("common.save")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
