import { type FormEvent, useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Input, Label } from "@/components/ui/Input";
import { useCreateCryptoPortfolio, useDeleteCryptoPortfolio, useUpdateCryptoPortfolio } from "@/hooks/useCrypto";
import { useTranslation } from "@/lib/i18n";
import type { CryptoPortfolio } from "@/types";

interface CryptoPortfolioFormModalProps {
  open: boolean;
  onClose: () => void;
  portfolio?: CryptoPortfolio | null;
  // Called after a successful delete — lets CryptoPage fall back to the
  // "All" tab when the portfolio it was showing just disappeared.
  onDeleted?: () => void;
}

/** Create/rename a portfolio, plus (when editing) archive and delete —
 * folded into one dialog rather than a separate management page, since a
 * portfolio is a lightweight grouping with only a name to edit. */
export function CryptoPortfolioFormModal({ open, onClose, portfolio, onDeleted }: CryptoPortfolioFormModalProps) {
  const { t } = useTranslation();
  const createPortfolio = useCreateCryptoPortfolio();
  const updatePortfolio = useUpdateCryptoPortfolio();
  const deletePortfolio = useDeleteCryptoPortfolio();

  const [name, setName] = useState("");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setName(portfolio?.name ?? "");
    setSaveError(null);
    setDeleteError(null);
  }, [open, portfolio]);

  const isSaving = createPortfolio.isPending || updatePortfolio.isPending;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSaveError(null);
    try {
      if (portfolio) {
        await updatePortfolio.mutateAsync({ id: portfolio.id, input: { name } });
      } else {
        await createPortfolio.mutateAsync({ name });
      }
      onClose();
    } catch {
      setSaveError(t("crypto.portfolio.form.saveError"));
    }
  }

  function handleToggleArchived() {
    if (!portfolio) return;
    updatePortfolio.mutate({ id: portfolio.id, input: { is_archived: !portfolio.is_archived } });
  }

  async function handleDelete() {
    if (!portfolio) return;
    if (!window.confirm(t("crypto.portfolio.confirmDelete", { name: portfolio.name }))) return;
    setDeleteError(null);
    try {
      await deletePortfolio.mutateAsync(portfolio.id);
      onDeleted?.();
      onClose();
    } catch {
      // 400 when the portfolio still has coins in it — the only realistic
      // failure mode here (see services/crypto_service.py's delete_portfolio).
      setDeleteError(t("crypto.portfolio.deleteError"));
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={portfolio ? t("crypto.portfolio.form.editTitle") : t("crypto.portfolio.form.newTitle")}
    >
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <Label htmlFor="portfolio-name">{t("crypto.portfolio.form.nameLabel")}</Label>
          <Input
            id="portfolio-name"
            autoFocus
            required
            maxLength={100}
            placeholder={t("crypto.portfolio.form.namePlaceholder")}
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </div>

        {saveError && <p className="text-sm text-danger">{saveError}</p>}

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" disabled={isSaving}>
            {isSaving ? t("common.saving") : t("common.save")}
          </Button>
        </div>

        {portfolio && (
          <div className="flex items-center justify-between border-t border-border pt-3">
            <button
              type="button"
              onClick={handleToggleArchived}
              className="text-xs font-medium text-text-muted hover:text-text-primary"
            >
              {portfolio.is_archived ? t("crypto.portfolio.unarchiveLabel") : t("crypto.portfolio.archiveLabel")}
            </button>
            <button type="button" onClick={handleDelete} className="text-xs font-medium text-danger hover:underline">
              {t("common.delete")}
            </button>
          </div>
        )}
        {deleteError && <p className="text-sm text-danger">{deleteError}</p>}
      </form>
    </Dialog>
  );
}
