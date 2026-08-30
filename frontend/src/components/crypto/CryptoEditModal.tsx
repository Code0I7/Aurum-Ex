import { type FormEvent, useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Input, Label } from "@/components/ui/Input";
import { useUpdateCryptoHoldingQuantity } from "@/hooks/useCrypto";
import { useTranslation } from "@/lib/i18n";
import type { CryptoHolding } from "@/types";

interface CryptoEditModalProps {
  open: boolean;
  onClose: () => void;
  holding: CryptoHolding | null;
}

/** Quantity only — editing never calls CoinGecko (see
 * services/crypto_service.py's update_holding_quantity): the value is
 * recomputed from the last known price instead. */
export function CryptoEditModal({ open, onClose, holding }: CryptoEditModalProps) {
  const { t } = useTranslation();
  const updateQuantity = useUpdateCryptoHoldingQuantity();

  const [quantity, setQuantity] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !holding) return;
    setQuantity(holding.quantity);
    setError(null);
  }, [open, holding]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!holding) return;
    setError(null);
    try {
      await updateQuantity.mutateAsync({ assetId: holding.asset_id, quantity });
      onClose();
    } catch {
      setError(t("crypto.form.saveError"));
    }
  }

  if (!holding) return null;

  return (
    <Dialog open={open} onClose={onClose} title={t("crypto.form.editTitle", { name: holding.name })}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <Label htmlFor="crypto-edit-quantity">{t("crypto.form.quantityLabel")}</Label>
          <Input
            id="crypto-edit-quantity"
            type="number"
            step="any"
            min="0"
            required
            autoFocus
            value={quantity}
            onChange={(event) => setQuantity(event.target.value)}
          />
        </div>

        {error && <p className="text-sm text-danger">{error}</p>}

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" disabled={updateQuantity.isPending}>
            {updateQuantity.isPending ? t("common.saving") : t("common.save")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
