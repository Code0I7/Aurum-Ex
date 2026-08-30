import { type FormEvent, useEffect, useState } from "react";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Input, Label } from "@/components/ui/Input";
import { useAddCryptoTransaction } from "@/hooks/useCrypto";
import { useTranslation } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { CryptoHolding, CryptoTransactionType } from "@/types";

interface CryptoTransactionModalProps {
  open: boolean;
  onClose: () => void;
  holding: CryptoHolding | null;
}

/** Buy more of, or sell some of, a coin already being tracked — the "+"
 * action on the holdings table. Never calls CoinGecko (see
 * services/crypto_service.py's add_transaction): value is recomputed from
 * the last cached price. */
export function CryptoTransactionModal({ open, onClose, holding }: CryptoTransactionModalProps) {
  const { t } = useTranslation();
  const addTransaction = useAddCryptoTransaction();

  const [type, setType] = useState<CryptoTransactionType>("buy");
  const [quantity, setQuantity] = useState("");
  const [pricePerUnit, setPricePerUnit] = useState("");
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setType("buy");
    setQuantity("");
    setPricePerUnit("");
    setDate(new Date().toISOString().slice(0, 10));
    setNote("");
    setError(null);
  }, [open, holding]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!holding) return;
    setError(null);
    try {
      await addTransaction.mutateAsync({
        assetId: holding.asset_id,
        input: { type, quantity, price_per_unit: pricePerUnit, date, note: note || null },
      });
      onClose();
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 400 ? t("crypto.form.errorSellTooMuch") : t("crypto.form.saveError")
      );
    }
  }

  if (!holding) return null;

  return (
    <Dialog open={open} onClose={onClose} title={t("crypto.form.tradeTitle", { name: holding.name })}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={() => setType("buy")}
            className={cn(
              "rounded-lg border px-3 py-2 text-sm font-medium transition-colors",
              type === "buy" ? "border-success bg-success/10 text-success" : "border-border text-text-secondary"
            )}
          >
            {t("crypto.form.buy")}
          </button>
          <button
            type="button"
            onClick={() => setType("sell")}
            className={cn(
              "rounded-lg border px-3 py-2 text-sm font-medium transition-colors",
              type === "sell" ? "border-danger bg-danger/10 text-danger" : "border-border text-text-secondary"
            )}
          >
            {t("crypto.form.sell")}
          </button>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label htmlFor="tx-quantity">{t("crypto.form.quantityLabel")}</Label>
            <Input
              id="tx-quantity"
              type="number"
              step="any"
              min="0"
              required
              autoFocus
              value={quantity}
              onChange={(event) => setQuantity(event.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="tx-price">{t("crypto.form.pricePerUnitLabel")}</Label>
            <Input
              id="tx-price"
              type="number"
              step="any"
              min="0"
              required
              value={pricePerUnit}
              onChange={(event) => setPricePerUnit(event.target.value)}
            />
          </div>
        </div>

        <div>
          <Label htmlFor="tx-date">{t("crypto.form.dateLabel")}</Label>
          <Input id="tx-date" type="date" required value={date} onChange={(event) => setDate(event.target.value)} />
        </div>

        <div>
          <Label htmlFor="tx-note">{t("crypto.form.noteLabel")}</Label>
          <Input id="tx-note" value={note} onChange={(event) => setNote(event.target.value)} />
        </div>

        {error && <p className="text-sm text-danger">{error}</p>}

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" disabled={addTransaction.isPending}>
            {addTransaction.isPending ? t("common.saving") : t("common.save")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
