import { type FormEvent, useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Input, Label } from "@/components/ui/Input";
import { useConfirm } from "@/components/ui/ConfirmProvider";
import { useCreatePortfolio, useDeletePortfolio, useUpdatePortfolio } from "@/hooks/useInvestments";
import { useTranslation } from "@/lib/i18n";
import type { InvestmentPortfolio } from "@/types";

interface PortfolioFormModalProps {
  open: boolean;
  onClose: () => void;
  /** Портфель, который правим. null — заводим новый. */
  portfolio?: InvestmentPortfolio | null;
  /** Вызывается после удаления: страница переключается на «Все». */
  onDeleted?: () => void;
}

/**
 * Завести, переименовать или удалить портфель.
 *
 * До этого портфель можно было создать ровно один раз — кнопкой на пустом
 * экране, — и дальше он оставался навсегда: ни второго, ни другого имени.
 * Разделение на портфели при этом и есть смысл вкладки: «долгосрочный» и
 * «спекулятивный» смотрят по-разному, и держать их в одной куче — то же
 * самое, что не разделять вовсе.
 *
 * Окно одно на все три действия, как у криптовалюты: портфель — это имя и
 * ничего больше, и заводить под него отдельный экран управления значило бы
 * сделать из одной строки ввода целый раздел.
 */
export function PortfolioFormModal({ open, onClose, portfolio, onDeleted }: PortfolioFormModalProps) {
  const { t } = useTranslation();
  const createPortfolio = useCreatePortfolio();
  const updatePortfolio = useUpdatePortfolio();
  const deletePortfolio = useDeletePortfolio();
  const confirm = useConfirm();

  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setName(portfolio?.name ?? "");
    setError(null);
  }, [open, portfolio]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    setError(null);
    try {
      if (portfolio) {
        await updatePortfolio.mutateAsync({ id: portfolio.id, input: { name: trimmed } });
      } else {
        await createPortfolio.mutateAsync({ name: trimmed });
      }
      onClose();
    } catch {
      setError(t("investments.portfolioSaveError"));
    }
  }

  async function handleDelete() {
    if (!portfolio) return;
    const ok = await confirm({
      message: t("investments.confirmDeletePortfolio", { name: portfolio.name }),
      confirmLabel: t("common.delete"),
      tone: "danger",
    });
    if (!ok) return;
    setError(null);
    try {
      await deletePortfolio.mutateAsync(portfolio.id);
      onDeleted?.();
      onClose();
    } catch {
      // Единственная причина отказа — непустой портфель: бумаги в нём
      // остались бы без владельца. Сообщение прямо говорит, что делать.
      setError(t("investments.portfolioDeleteError"));
    }
  }

  const isBusy = createPortfolio.isPending || updatePortfolio.isPending || deletePortfolio.isPending;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={portfolio ? t("investments.editPortfolio") : t("investments.newPortfolio")}
    >
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <Label htmlFor="portfolio-name">{t("investments.portfolioName")}</Label>
          <Input
            id="portfolio-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder={t("investments.portfolioNamePlaceholder")}
            autoFocus
            required
          />
        </div>

        {error && <p className="text-sm text-danger">{error}</p>}

        <div className="flex items-center justify-between gap-2 pt-1">
          {/* Удаление слева и неброско: оно здесь возможно, но не
              предлагается — окно открывают, чтобы переименовать. */}
          {portfolio ? (
            <Button type="button" variant="ghost" onClick={handleDelete} disabled={isBusy}>
              {t("common.delete")}
            </Button>
          ) : (
            <span />
          )}
          <span className="flex gap-2">
            <Button type="button" variant="ghost" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={isBusy || name.trim() === ""}>
              {t("common.save")}
            </Button>
          </span>
        </div>
      </form>
    </Dialog>
  );
}
