import { useState } from "react";
import { Plus } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { ProductList } from "@/components/products/ProductList";
import { ProductFormModal } from "@/components/products/ProductFormModal";
import { PriceHistoryModal } from "@/components/products/PriceHistoryModal";
import { useDeleteProduct,
  useUpdateProduct, useProducts } from "@/hooks/useProducts";
import { useTranslation } from "@/lib/i18n";
import { useConfirm } from "@/components/ui/ConfirmProvider";
import type { Product } from "@/types";

/**
 * Справочник товаров.
 *
 * Нужен раньше, чем позиции чека становятся осмысленными: десять чеков со
 * словом «хлеб» — десять несвязанных строк, а десять позиций, указывающих
 * на одну строку справочника, — кривая цены.
 */
export function ProductsPage() {
  const { t } = useTranslation();
  const [showArchived, setShowArchived] = useState(false);
  const { data: products, isLoading } = useProducts(showArchived);
  const deleteProduct = useDeleteProduct();
  const updateProduct = useUpdateProduct();
  const confirm = useConfirm();

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Product | null>(null);
  const [pricesFor, setPricesFor] = useState<Product | null>(null);

  function openCreate() {
    setEditing(null);
    setFormOpen(true);
  }

  async function handleDelete(product: Product) {
    const ok = await confirm({
      message: t("product.confirmDelete", { name: product.name }),
      confirmLabel: t("common.delete"),
      tone: "danger",
    });
    if (ok) deleteProduct.mutate(product.id);
  }

  return (
    <div className="space-y-5">
      {/* Переключатель стоит над карточкой, а не внутри неё: он относится
          ко всему списку, а не к какой-то его части, и в справочниках
          «Люди и места» он стоит там же. */}
      <div className="flex justify-end">
        <label className="flex cursor-pointer items-center gap-2 text-sm text-text-secondary">
          <input
            type="checkbox"
            checked={showArchived}
            onChange={(event) => setShowArchived(event.target.checked)}
            className="h-3.5 w-3.5 accent-text-primary"
          />
          {t("product.showArchived")}
        </label>
      </div>

      <Card>
        <CardHeader className="items-start">
          <div>
            <CardTitle>{t("nav.products")}</CardTitle>
            <p className="mt-1 text-xs text-text-muted">{t("product.subtitle")}</p>
          </div>
          <Button onClick={openCreate}>
            <Plus size={16} />
            {t("common.add")}
          </Button>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="py-10 text-center text-sm text-text-muted">{t("common.loading")}</p>
          ) : (
            <ProductList
              items={products ?? []}
              onEdit={(product) => {
                setEditing(product);
                setFormOpen(true);
              }}
              onPrices={setPricesFor}
              onDelete={handleDelete}
              onArchive={(product) =>
                updateProduct.mutate({
                  id: product.id,
                  input: { is_archived: !product.is_archived },
                })
              }
            />
          )}
        </CardContent>
      </Card>

      <ProductFormModal open={formOpen} onClose={() => setFormOpen(false)} product={editing} />
      <PriceHistoryModal product={pricesFor} onClose={() => setPricesFor(null)} />
    </div>
  );
}
