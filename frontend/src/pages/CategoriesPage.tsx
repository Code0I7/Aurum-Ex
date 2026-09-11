import { useMemo, useState } from "react";
import { Plus } from "lucide-react";
import { PageActions } from "@/components/layout/PageActions";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { CategoryFormModal } from "@/components/categories/CategoryFormModal";
import { CategoryList } from "@/components/categories/CategoryList";
import { useCategoryTotals, useCategories, useDeleteCategory } from "@/hooks/useCategories";
import { translateCategoryName } from "@/lib/categoryLabels";
import { useTranslation } from "@/lib/i18n";
import { useConfirm } from "@/components/ui/ConfirmProvider";
import { fetchCategoryUsage } from "@/api/categories";
import type { Category, CategoryKind, CategoryUsage } from "@/types";

// Alphabetical by displayed (translated) name — same locale-aware sort
// BudgetFormModal's category picker uses, so a default category shown as
// its localized name sorts by that, not its raw stored English name.
function byName(language: string) {
  return (a: Category, b: Category) =>
    translateCategoryName(a.name).localeCompare(translateCategoryName(b.name), language);
}

// Абзацы вопроса разделяются пустой строкой: Dialog рендерит текст с
// whitespace-pre-line, и последствие удаления читается отдельно от
// самого вопроса, а не сливается с ним в один абзац.
const PARAGRAPH_BREAK = "\n\n";

export function CategoriesPage() {
  // Суммы за всё время: список категорий открывают, чтобы разобраться в
  // накопившемся, а не посмотреть текущий месяц.
  const { data: totals } = useCategoryTotals();
  const totalsById = useMemo(
    () => new Map((totals ?? []).map((row) => [row.category_id, row])),
    [totals],
  );
  const { t, language } = useTranslation();
  const { data: categories, isLoading } = useCategories();
  const deleteCategory = useDeleteCategory();
  const confirm = useConfirm();

  const [modalOpen, setModalOpen] = useState(false);
  const [editingCategory, setEditingCategory] = useState<Category | null>(null);
  const [modalKind, setModalKind] = useState<CategoryKind>("expense");

  function openCreateModal(kind: CategoryKind) {
    setEditingCategory(null);
    setModalKind(kind);
    setModalOpen(true);
  }

  function openEditModal(category: Category) {
    setEditingCategory(category);
    setModalKind(category.kind);
    setModalOpen(true);
  }

  async function handleDelete(category: Category) {
    // Вопрос собирается из того, что удаление действительно зацепит.
    // Безразмерное «её транзакции останутся без категории» выглядело
    // одинаково и для пустой категории, и для той, в которой лежит год
    // истории, — решение принималось вслепую. Про подкатегории оно молчало
    // совсем, хотя они переживают родителя и всплывают в корень.
    let usage: CategoryUsage | null = null;
    try {
      usage = await fetchCategoryUsage(category.id);
    } catch {
      // Не достучались — спрашиваем без чисел. Молча удалять из-за сбоя
      // подсчёта нельзя, а отменять действие целиком незачем.
      usage = null;
    }

    const lines = [t("category.confirmDelete", { name: category.name })];
    if (usage) {
      if (usage.transactions > 0) lines.push(t("category.deleteUsed", { count: usage.transactions }));
      if (usage.transactions === 0 && usage.children === 0) {
        lines.push(t("category.deleteUnused"));
      }
      if (usage.children > 0) {
        lines.push(t("category.deleteChildren", { count: usage.children }));
        // Внуки называются отдельно: «две подкатегории» звучит безобидно,
        // когда под ними ещё двадцать.
        if (usage.descendants > usage.children) {
          lines.push(
            t("category.deleteBranch", {
              descendants: usage.descendants,
              transactions: usage.descendant_transactions,
            }),
          );
        }
      }
    } else {
      lines.push(t("category.deleteUnknownUsage"));
    }

    const ok = await confirm({
      message: lines.join(PARAGRAPH_BREAK),
      confirmLabel: t("common.delete"),
      tone: "danger",
    });
    if (!ok) return;
    try {
      await deleteCategory.mutateAsync(category.id);
    } catch {
      // The only way a delete 400s is a default category that still has
      // transactions pointing at it (api/routes/categories.py) — a custom
      // category has no such guard and always succeeds.
      await confirm({ message: t("category.defaultDeleteBlocked"), acknowledgeOnly: true });
    }
  }

  const expenseCategories = (categories ?? []).filter((category) => category.kind === "expense").sort(byName(language));
  const incomeCategories = (categories ?? []).filter((category) => category.kind === "income").sort(byName(language));

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>{t("category.incomeSectionTitle")}</CardTitle>
          {/* Здесь действий два — доходная категория и расходная, — и в
              шапке они подписаны по виду. Просто «Добавить» дважды рядом
              не сказало бы, что чем отличается: на странице это объясняли
              заголовки разделов, а в шапке заголовков нет. */}
          <PageActions>
            <Button variant="secondary" onClick={() => openCreateModal("income")}>
              <Plus size={16} />
              {t("transactions.income")}
            </Button>
          </PageActions>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="py-10 text-center text-sm text-text-muted">{t("common.loading")}</p>
          ) : (
            <CategoryList
              items={incomeCategories}
              totals={totalsById}
              onEdit={openEditModal}
              onDelete={handleDelete}
            />
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("category.expenseSectionTitle")}</CardTitle>
          <PageActions>
            <Button onClick={() => openCreateModal("expense")}>
              <Plus size={16} />
              {t("transactions.expense")}
            </Button>
          </PageActions>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="py-10 text-center text-sm text-text-muted">{t("common.loading")}</p>
          ) : (
            <CategoryList
              items={expenseCategories}
              totals={totalsById}
              onEdit={openEditModal}
              onDelete={handleDelete}
            />
          )}
        </CardContent>
      </Card>

      <CategoryFormModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        category={editingCategory}
        defaultKind={modalKind}
      />
    </div>
  );
}
