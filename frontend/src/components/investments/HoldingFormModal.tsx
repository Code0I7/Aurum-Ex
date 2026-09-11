import { useEffect, useState } from "react";
import { Combobox } from "@/components/ui/Combobox";
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
          <Combobox
            id="holding-portfolio"
            className="mt-1"
            options={portfolios.map((portfolio) => ({ value: String(portfolio.id), label: portfolio.name }))}
            value={form.portfolio_id}
            onChange={(value) => setForm((prev) => ({ ...prev, portfolio_id: value }))}
            placeholder={t("investments.portfolio")}
          />
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
          <Combobox
            id="holding-kind"
            className="mt-1"
            options={KINDS.map((kind) => ({
              value: kind,
              label: t(`investments.kind.${kind}` as never),
            }))}
            value={form.kind}
            onChange={(value) => setForm((prev) => ({ ...prev, kind: value as InvestmentKind }))}
            placeholder={t(`investments.kind.${KINDS[0]}` as never)}
          />
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
