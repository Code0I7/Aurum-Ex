import { useState } from "react";
import { Plus } from "lucide-react";
import { PageActions } from "@/components/layout/PageActions";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { RecurringList } from "@/components/recurring/RecurringList";
import { RecurringFormModal } from "@/components/recurring/RecurringFormModal";
import { useDeleteRecurring, usePostRecurring, useRecurring } from "@/hooks/useRecurring";
import { useTranslation } from "@/lib/i18n";
import { useConfirm } from "@/components/ui/ConfirmProvider";
import type { RecurringTransaction } from "@/types";

export function RecurringPage() {
  const { t } = useTranslation();
  const { data: items, isLoading } = useRecurring();
  const deleteRecurring = useDeleteRecurring();
  const confirm = useConfirm();
  const postRecurring = usePostRecurring();

  const [modalOpen, setModalOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<RecurringTransaction | null>(null);

  function openCreateModal() {
    setEditingItem(null);
    setModalOpen(true);
  }

  function openEditModal(item: RecurringTransaction) {
    setEditingItem(item);
    setModalOpen(true);
  }

  async function handleDelete(item: RecurringTransaction) {
    const ok = await confirm({
      message: t("recurring.confirmDelete", { name: item.description }),
      confirmLabel: t("common.delete"),
      tone: "danger",
    });
    if (ok) deleteRecurring.mutate(item.id);
  }

  function handlePost(item: RecurringTransaction) {
    postRecurring.mutate(item.id);
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>{t("nav.recurring")}</CardTitle>
          <PageActions>
            <Button onClick={openCreateModal}>
              <Plus size={16} />
              {t("common.add")}
            </Button>
          </PageActions>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="py-10 text-center text-sm text-text-muted">{t("common.loading")}</p>
          ) : (
            <RecurringList
              items={items ?? []}
              onPost={handlePost}
              onEdit={openEditModal}
              onDelete={handleDelete}
              isPosting={postRecurring.isPending}
            />
          )}
        </CardContent>
      </Card>

      <RecurringFormModal open={modalOpen} onClose={() => setModalOpen(false)} recurring={editingItem} />
    </div>
  );
}
