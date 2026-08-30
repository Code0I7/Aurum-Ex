import { type FormEvent, useEffect, useState } from "react";
import { ApiError } from "@/api/client";
import { searchCryptoCoins } from "@/api/crypto";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Input, Label } from "@/components/ui/Input";
import { useCreateCryptoHolding } from "@/hooks/useCrypto";
import { useTranslation } from "@/lib/i18n";
import type { CryptoSearchResult } from "@/types";

interface CryptoAddModalProps {
  open: boolean;
  onClose: () => void;
}

/** Two phases in one dialog: search CoinGecko for a coin, then pick one and
 * enter how much of it is held. No separate multi-step wizard — unlike CSV
 * import, there's nothing here worth a dedicated page for. */
export function CryptoAddModal({ open, onClose }: CryptoAddModalProps) {
  const { t } = useTranslation();
  const createHolding = useCreateCryptoHolding();

  const [query, setQuery] = useState("");
  const [results, setResults] = useState<CryptoSearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [selected, setSelected] = useState<CryptoSearchResult | null>(null);
  const [quantity, setQuantity] = useState("");
  const [pricePerUnit, setPricePerUnit] = useState("");
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (open) return;
    setQuery("");
    setResults([]);
    setSelected(null);
    setQuantity("");
    setPricePerUnit("");
    setDate(new Date().toISOString().slice(0, 10));
    setSearchError(null);
    setSaveError(null);
  }, [open]);

  useEffect(() => {
    if (!open || selected) return;
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setResults([]);
      setSearchError(null);
      return;
    }
    setSearching(true);
    setSearchError(null);
    const timer = setTimeout(async () => {
      try {
        setResults(await searchCryptoCoins(trimmed));
      } catch (error) {
        setResults([]);
        setSearchError(
          error instanceof ApiError && error.status === 400 ? t("crypto.search.noApiKey") : t("crypto.form.saveError")
        );
      } finally {
        setSearching(false);
      }
    }, 400);
    return () => clearTimeout(timer);
  }, [query, open, selected, t]);

  async function handleSave(event: FormEvent) {
    event.preventDefault();
    if (!selected) return;
    setSaveError(null);
    try {
      await createHolding.mutateAsync({
        coingecko_id: selected.coingecko_id,
        symbol: selected.symbol,
        name: selected.name,
        thumb_url: selected.thumb_url,
        quantity,
        price_per_unit: pricePerUnit,
        date,
      });
      onClose();
    } catch {
      setSaveError(t("crypto.form.saveError"));
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={selected ? t("crypto.form.addTitle", { name: selected.name }) : t("crypto.addButton")}
    >
      {!selected ? (
        <div className="space-y-3">
          <Input
            autoFocus
            placeholder={t("crypto.search.placeholder")}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          {searchError && <p className="text-sm text-danger">{searchError}</p>}
          {!searchError && query.trim().length < 2 && (
            <p className="text-sm text-text-muted">{t("crypto.search.hint")}</p>
          )}
          {searching && <p className="text-sm text-text-muted">{t("common.loading")}</p>}
          {!searching && !searchError && query.trim().length >= 2 && results.length === 0 && (
            <p className="text-sm text-text-muted">{t("crypto.search.empty")}</p>
          )}
          <ul className="max-h-72 space-y-1 overflow-y-auto">
            {results.map((coin) => (
              <li key={coin.coingecko_id}>
                <button
                  type="button"
                  onClick={() => setSelected(coin)}
                  className="flex w-full items-center gap-3 rounded-lg p-2 text-left hover:bg-surface-2"
                >
                  {coin.thumb_url ? (
                    <img src={coin.thumb_url} alt="" className="h-6 w-6 shrink-0 rounded-full" />
                  ) : (
                    <span className="h-6 w-6 shrink-0 rounded-full bg-surface-2" />
                  )}
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-text-primary">{coin.name}</span>
                    <span className="block text-xs text-text-muted">{coin.symbol}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <form onSubmit={handleSave} className="space-y-3">
          <div className="flex items-center gap-3 rounded-lg bg-surface-2 p-2">
            {selected.thumb_url ? (
              <img src={selected.thumb_url} alt="" className="h-6 w-6 shrink-0 rounded-full" />
            ) : (
              <span className="h-6 w-6 shrink-0 rounded-full bg-surface-1" />
            )}
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium text-text-primary">{selected.name}</span>
              <span className="block text-xs text-text-muted">{selected.symbol}</span>
            </span>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="crypto-quantity">{t("crypto.form.quantityLabel")}</Label>
              <Input
                id="crypto-quantity"
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
              <Label htmlFor="crypto-price">{t("crypto.form.pricePerUnitLabel")}</Label>
              <Input
                id="crypto-price"
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
            <Label htmlFor="crypto-date">{t("crypto.form.dateLabel")}</Label>
            <Input
              id="crypto-date"
              type="date"
              required
              value={date}
              onChange={(event) => setDate(event.target.value)}
            />
          </div>

          {saveError && <p className="text-sm text-danger">{saveError}</p>}

          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="ghost" onClick={() => setSelected(null)}>
              {t("common.back")}
            </Button>
            <Button type="submit" disabled={createHolding.isPending}>
              {createHolding.isPending ? t("common.saving") : t("common.save")}
            </Button>
          </div>
        </form>
      )}
    </Dialog>
  );
}
