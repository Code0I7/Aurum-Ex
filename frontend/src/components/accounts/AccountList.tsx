import { Archive, ArchiveRestore, Banknote, Bitcoin, CreditCard, Landmark, Package, Pencil, PiggyBank, TrendingUp, Trash2, Wallet, type LucideIcon } from "lucide-react";
import { formatCurrency } from "@/lib/format";
import { useTranslation, type TranslationKey } from "@/lib/i18n";
import type { AccountKind, AccountWithBalance } from "@/types";

interface AccountListProps {
  items: AccountWithBalance[];
  // Счёт целиком, а не одно его имя: форме нужно число операций — она
  // предупреждает, сколько записей пересчитает смена валюты.
  onEdit: (account: AccountWithBalance) => void;
  onToggleArchived: (account: AccountWithBalance) => void;
  onDelete: (account: AccountWithBalance) => void;
}

const KIND_ICONS: Record<AccountKind, LucideIcon> = {
  checking: Wallet,
  savings: PiggyBank,
  credit_card: CreditCard,
  cash: Banknote,
  investment: TrendingUp,
  crypto: Bitcoin,
  // Кредит или рассрочка без пластика — тот же долг банку, что и по карте,
  // но выглядеть как карта не должен.
  loan: Landmark,
  other: Package,
};

export function AccountList({ items, onEdit, onToggleArchived, onDelete }: AccountListProps) {
  const { t, currency: base } = useTranslation();

  if (items.length === 0) {
    return <p className="py-10 text-center text-sm text-text-muted">{t("account.empty")}</p>;
  }

  return (
    <ul className="divide-y divide-gridline">
      {items.map((account) => {
        const Icon = KIND_ICONS[account.kind];
        const balance = Number(account.balance);
        const reserved = Number(account.reserved ?? 0);

        return (
          <li key={account.id} className={`flex items-center gap-3 py-3 ${account.is_archived ? "opacity-50" : ""}`}>
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-surface-2">
              <Icon size={16} className="text-text-secondary" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="flex items-center gap-1.5 truncate text-sm font-medium text-text-primary">
                {account.name}
                {account.is_archived && (
                  <span className="shrink-0 rounded bg-surface-2 px-1 py-0.5 text-[10px] leading-none text-text-muted">
                    {t("account.archivedBadge")}
                  </span>
                )}
              </span>
              <span className="block truncate text-xs text-text-muted">
                {t(`account.kind.${account.kind}` as TranslationKey)}
                {/* Резерв дописывается к виду счёта, а не отдельной строкой:
                    у большинства счетов его нет, и пустая строка растянула бы
                    список без пользы. Баланс при этом не уменьшается — деньги
                    лежат там же, просто часть обещана цели. */}
                {reserved > 0 && (
                  <>
                    {" · "}
                    {t("account.reservedShort", { amount: formatCurrency(reserved, account.currency) })}
                  </>
                )}
                {/* Начального остатка в строке нет: он свойство счёта, а не
                    ответ на «сколько у меня сейчас», и читают его, открыв сам
                    счёт. В списке он был бы четвёртым числом в строке. */}
              </span>
            </span>
            <span className="shrink-0 text-right">
              <span
                className="block text-sm font-medium tabular-nums"
                style={{ color: balance < 0 ? "var(--danger)" : "var(--text-primary)" }}
              >
                {formatCurrency(balance, account.currency)}
              </span>
              {/* Второе число — тот же остаток в валюте установки, по
                  сегодняшнему курсу. Показывается только у валютного счёта:
                  у рублёвого это было бы то же самое число дважды.

                  По сегодняшнему, а не по курсу дня операции: сто долларов
                  на карте стоят столько, сколько стоят сейчас. Трата
                  прошлого года так и осталась тратой прошлого года — это
                  разные вопросы, и отвечают на них по-разному. */}
              {account.currency !== base && (
                <span className="block text-xs tabular-nums text-text-muted">
                  ≈ {formatCurrency(account.balance_base, base)}
                </span>
              )}
              {reserved > 0 && (
                <span className="block text-xs tabular-nums text-text-muted">
                  {t("account.availableShort", { amount: formatCurrency(account.available, account.currency) })}
                </span>
              )}
            </span>
            <span className="flex shrink-0 gap-1">
              <button
                type="button"
                aria-label={account.is_archived ? t("account.unarchiveLabel") : t("account.archiveLabel")}
                onClick={() => onToggleArchived(account)}
                className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
              >
                {account.is_archived ? <ArchiveRestore size={15} /> : <Archive size={15} />}
              </button>
              <button
                type="button"
                aria-label={t("common.edit")}
                onClick={() => onEdit(account)}
                className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
              >
                <Pencil size={15} />
              </button>
              <button
                type="button"
                aria-label={t("common.delete")}
                onClick={() => onDelete(account)}
                className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-danger"
              >
                <Trash2 size={15} />
              </button>
            </span>
          </li>
        );
      })}
    </ul>
  );
}
