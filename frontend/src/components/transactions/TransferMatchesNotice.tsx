import { useState } from "react";
import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { useDismissTransferMatch, useMergeTransferMatch, useTransferMatches } from "@/hooks/useTransferMatches";
import { formatCurrency, formatTransactionDate } from "@/lib/format";
import { useTranslation, type TranslationKey } from "@/lib/i18n";
import { translateCategoryName } from "@/lib/categoryLabels";
import type { TransferMatch, TransferMatchSide } from "@/types";

// В паре бывают только эти три вида: расчёты с людьми в поиск не входят.
const TYPE_LABEL_KEYS: Partial<Record<TransferMatchSide["type"], TranslationKey>> = {
  expense: "transactions.form.typeExpense",
  income: "transactions.form.typeIncome",
  transfer: "transactions.form.typeTransfer",
};

/**
 * Одна запись пары: счёт (или маршрут перевода), дата, вид и сумма.
 *
 * Общая для окна проверки и для вопроса в форме: одна и та же запись
 * должна выглядеть одинаково в обоих местах, иначе человек не узнает её
 * при второй встрече.
 */
export function TransferMatchSideRow({ side, note, noteTone }: {
  side: TransferMatchSide;
  /** Что станет с записью — «останется», «удалится». Без подписи в форме. */
  note?: string;
  noteTone?: "danger" | "muted";
}) {
  const { t } = useTranslation();
  const detail = side.description || (side.category_name ? translateCategoryName(side.category_name) : "");
  return (
    <span className="flex items-start justify-between gap-3 py-2 first:pt-0 last:pb-0">
      <span className="min-w-0">
        <span className="flex min-w-0 items-center gap-1 text-sm text-text-primary">
          <span className="truncate">{side.account_name}</span>
          {side.transfer_account_name && (
            <>
              <ArrowRight size={13} className="shrink-0 text-text-muted" />
              <span className="truncate">{side.transfer_account_name}</span>
            </>
          )}
        </span>
        <span className="block truncate text-xs text-text-muted">
          {formatTransactionDate(side.date, true)} · {t(TYPE_LABEL_KEYS[side.type] ?? "transactions.form.typeExpense")}
          {detail ? ` · ${detail}` : ""}
        </span>
      </span>
      <span className="shrink-0 text-right">
        <span className="block text-sm font-medium tabular-nums text-text-primary">
          {formatCurrency(side.amount, side.currency)}
        </span>
        {note && (
          <span className={`block text-xs ${noteTone === "danger" ? "text-danger" : "text-text-muted"}`}>{note}</span>
        )}
      </span>
    </span>
  );
}

/** Каким станет перевод после склейки: откуда, куда, когда и сколько. */
function mergedRoute(match: TransferMatch) {
  if (match.kind === "halves") {
    // Трата становится переводом на счёт дохода и сохраняет свою дату.
    return { date: match.keep.date, from: match.keep.account_name, to: match.drop.account_name };
  }
  return {
    date: match.keep.date,
    from: match.keep.account_name,
    to: match.keep.transfer_account_name ?? "—",
  };
}

function MatchCard({ match }: { match: TransferMatch }) {
  const { t } = useTranslation();
  const merge = useMergeTransferMatch();
  const dismiss = useDismissTransferMatch();
  const [failed, setFailed] = useState(false);
  const busy = merge.isPending || dismiss.isPending;
  const route = mergedRoute(match);
  const ids = { keepId: match.keep.id, dropId: match.drop.id };

  return (
    <li className="rounded-lg border border-border p-3">
      <p className="mb-2 text-xs font-medium text-text-muted">{t(`transferMatches.kind.${match.kind}`)}</p>
      <span className="block divide-y divide-gridline">
        <TransferMatchSideRow
          side={match.keep}
          note={t(match.kind === "halves" ? "transferMatches.becomesTransfer" : "transferMatches.stays")}
        />
        <TransferMatchSideRow side={match.drop} note={t("transferMatches.removed")} noteTone="danger" />
      </span>
      <p className="mt-2 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 border-t border-gridline pt-2 text-sm text-text-primary">
        <span className="text-text-muted">{t("transferMatches.result")}</span>
        <span className="inline-flex min-w-0 items-center gap-1">
          <span className="truncate">{route.from}</span>
          <ArrowRight size={13} className="shrink-0 text-text-muted" />
          <span className="truncate">{route.to}</span>
        </span>
        <span className="text-text-muted">
          · {formatTransactionDate(route.date, true)} ·{" "}
          <span className="tabular-nums text-text-primary">{formatCurrency(match.keep.amount, match.keep.currency)}</span>
        </span>
      </p>
      {failed && <p className="mt-2 text-xs text-danger">{t("transferMatches.mergeError")}</p>}
      <div className="mt-3 flex flex-wrap justify-end gap-2">
        {/* Отказ тише склейки: чаще всего пара и правда повтор, а честное
            совпадение — исключение. */}
        <Button
          variant="ghost"
          disabled={busy}
          onClick={() => {
            setFailed(false);
            dismiss.mutate(ids, { onError: () => setFailed(true) });
          }}
        >
          {t("transferMatches.dismiss")}
        </Button>
        <Button
          disabled={busy}
          onClick={() => {
            setFailed(false);
            merge.mutate(ids, { onError: () => setFailed(true) });
          }}
        >
          {t("transferMatches.merge")}
        </Button>
      </div>
    </li>
  );
}

/**
 * Плашка «похоже, переводы записаны дважды» и окно, где их разбирают.
 *
 * Перевод заносят по выпискам, а выписок две — по банку на каждую сторону,
 * и один перевод легко оказывается в приложении дважды. Склеивать само
 * приложение не берётся: совпадение суммы и дня бывает честным, а удалённую
 * запись назад не вернуть. Поэтому каждая пара показывается целиком — что
 * останется, что удалится и каким станет перевод, — и решает человек.
 *
 * Пока пар нет, плашки нет вовсе: место на странице операций дорогое.
 */
export function TransferMatchesNotice() {
  const { t } = useTranslation();
  const { data } = useTransferMatches();
  const [open, setOpen] = useState(false);
  const matches = data ?? [];

  if (matches.length === 0 && !open) return null;

  return (
    <>
      {matches.length > 0 && (
        <div className="flex flex-col gap-2 rounded-lg border border-accent/30 bg-accent/10 px-4 py-3 text-sm text-text-primary sm:flex-row sm:items-center sm:justify-between">
          <span>{t("transferMatches.notice", { count: matches.length })}</span>
          <Button variant="secondary" onClick={() => setOpen(true)} className="self-start whitespace-nowrap sm:self-auto">
            {t("transferMatches.review")}
          </Button>
        </div>
      )}
      <Dialog wide open={open} onClose={() => setOpen(false)} title={t("transferMatches.title")}>
        {matches.length === 0 ? (
          // Последняя пара разобрана, а окно ещё открыто: сказать, что
          // разбирать больше нечего, а не показать пустоту.
          <p className="py-8 text-center text-sm text-text-muted">{t("transferMatches.allDone")}</p>
        ) : (
          <ul className="space-y-3">
            {matches.map((match) => (
              <MatchCard key={`${match.keep.id}-${match.drop.id}`} match={match} />
            ))}
          </ul>
        )}
      </Dialog>
    </>
  );
}
