import { useEffect, useState } from "react";
import { Dialog } from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { Input, Label } from "@/components/ui/Input";
import { useCreateHolding } from "@/hooks/useInvestments";
import { useTranslation } from "@/lib/i18n";
import type { InvestmentKind, InvestmentPortfolio } from "@/types";

interface HoldingFormModalProps {
  open: boolean;
  onClose: () => void;
  portfolios: InvestmentPortfolio[];
  defaultPortfolioId: number | null;
}

const KINDS: InvestmentKind[] = ["stock", "bond", "fund", "crypto", "metal", "other"];

export function HoldingFormModal({ open, onClose, portfolios, defaultPortfolioId }: HoldingFormModalProps) {
  const { t } = useTranslation();
  const createHolding = useCreateHolding();

  const [form, setForm] = useState({ portfolio_id: "", name: "", ticker: "", kind: "stock" as InvestmentKind });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setForm({
      portfolio_id: String(defaultPortfolioId ?? portfolios[0]?.id ?? ""),
      name: "",
      ticker: "",
      kind: "stock",
    });
  }, [open, defaultPortfolioId, portfolios]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await createHolding.mutateAsync({
        portfolio_id: Number(form.portfolio_id),
        name: form.name.trim(),
        ticker: form.ticker.trim() || null,
        kind: form.kind,
      });
      onClose();
    } catch {
      setError(t("investments.saveError"));
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title={t("investments.newHolding")}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <Label htmlFor="holding-portfolio">{t("investments.portfolio")}</Label>
          <select
            id="holding-portfolio"
            value={form.portfolio_id}
            onChange={(event) => setForm((prev) => ({ ...prev, portfolio_id: event.target.value }))}
            className="mt-1 w-full rounded-md border border-border bg-surface-1 px-3 py-2 text-sm"
          >
            {portfolios.map((portfolio) => (
              <option key={portfolio.id} value={portfolio.id}>
                {portfolio.name}
              </option>
            ))}
          </select>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <Label htmlFor="holding-name">{t("investments.name")}</Label>
            <Input
              id="holding-name"
              required
              value={form.name}
              onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
            />
          </div>
          <div>
            <Label htmlFor="holding-ticker">{t("investments.ticker")}</Label>
            <Input
              id="holding-ticker"
              placeholder="ACME"
              value={form.ticker}
              onChange={(event) => setForm((prev) => ({ ...prev, ticker: event.target.value }))}
            />
          </div>
        </div>

        <div>
          <Label htmlFor="holding-kind">{t("investments.kindLabel")}</Label>
          <select
            id="holding-kind"
            value={form.kind}
            onChange={(event) => setForm((prev) => ({ ...prev, kind: event.target.value as InvestmentKind }))}
            className="mt-1 w-full rounded-md border border-border bg-surface-1 px-3 py-2 text-sm"
          >
            {KINDS.map((kind) => (
              <option key={kind} value={kind}>
                {t(`investments.kind.${kind}` as never)}
              </option>
            ))}
          </select>
          <p className="mt-1 text-xs text-text-muted">{t("investments.kindHint")}</p>
        </div>

        {error && <p className="text-sm text-danger">{error}</p>}

        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" disabled={createHolding.isPending}>
            {t("common.save")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
