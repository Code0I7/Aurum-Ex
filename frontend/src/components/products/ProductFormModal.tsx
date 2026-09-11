import { useEffect, useState } from "react";
import { Combobox } from "@/components/ui/Combobox";
import { Dialog } from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { Input, Label } from "@/components/ui/Input";
import { useCreateProduct, useUnits, useUpdateProduct } from "@/hooks/useProducts";
import { useTranslation } from "@/lib/i18n";
import type { Product } from "@/types";

interface ProductFormModalProps {
  open: boolean;
  onClose: () => void;
  product?: Product | null;
}

const EMPTY_FORM = { name: "", unit_id: "", barcode: "", notes: "" };

export function ProductFormModal({ open, onClose, product }: ProductFormModalProps) {
  const { t } = useTranslation();
  const createProduct = useCreateProduct();
  const updateProduct = useUpdateProduct();
  const { data: units } = useUnits();

  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    if (product) {
      setForm({
        name: product.name,
        unit_id: product.unit_id?.toString() ?? "",
        barcode: product.barcode ?? "",
        notes: product.notes ?? "",
      });
    } else {
      setForm(EMPTY_FORM);
    }
  }, [open, product]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    const input = {
      name: form.name.trim(),
      unit_id: form.unit_id ? Number(form.unit_id) : null,
      barcode: form.barcode.trim() || null,
      notes: form.notes.trim() || null,
    };

    try {
      if (product) {
        await updateProduct.mutateAsync({ id: product.id, input });
      } else {
        await createProduct.mutateAsync(input);
      }
      onClose();
    } catch {
      setError(t("product.saveError"));
    }
  }

  const isSaving = createProduct.isPending || updateProduct.isPending;

  return (
    <Dialog open={open} onClose={onClose} title={product ? t("product.editTitle") : t("product.newTitle")}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <Label htmlFor="product-name">{t("product.name")}</Label>
          <Input
            id="product-name"
            required
            placeholder={t("product.namePlaceholder")}
            value={form.name}
            onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
          />
        </div>

        {/* Категории у товара нет: она копировалась в позицию чека, где её
            не читал ни один отчёт. Деньги считаются по категории операции. */}
        <div className="grid gap-3">
          <div>
            <Label htmlFor="product-unit">{t("product.unit")}</Label>
            <Combobox
              id="product-unit"
              className="mt-1"
              options={(units ?? []).map((unit) => ({ value: String(unit.id), label: unit.name }))}
              value={form.unit_id}
              onChange={(value) => setForm((prev) => ({ ...prev, unit_id: value }))}
              placeholder={t("product.noUnit")}
              emptyLabel={t("product.noUnit")}
            />
          </div>
        </div>
        <p className="text-xs text-text-muted">{t("product.hintsHint")}</p>

        <div>
          <Label htmlFor="product-barcode">{t("product.barcode")}</Label>
          <Input
            id="product-barcode"
            inputMode="numeric"
            value={form.barcode}
            onChange={(event) => setForm((prev) => ({ ...prev, barcode: event.target.value }))}
          />
          <p className="mt-1 text-xs text-text-muted">{t("product.barcodeHint")}</p>
        </div>

        <div>
          <Label htmlFor="product-notes">{t("product.notes")}</Label>
          <Input
            id="product-notes"
            value={form.notes}
            onChange={(event) => setForm((prev) => ({ ...prev, notes: event.target.value }))}
          />
        </div>

        {error && <p className="text-sm text-danger">{error}</p>}

        <div className="flex justify-end gap-2 pt-1">
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
