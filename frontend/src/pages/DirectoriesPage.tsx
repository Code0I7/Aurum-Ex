import { useState } from "react";
import { Archive, ArchiveRestore, Check, Pencil, Plus, Trash2, X } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { HelpBadge } from "@/components/ui/HelpBadge";
import {
  useCounterparties,
  useCreateCounterparty,
  useCreateParticipant,
  useCreateStore,
  useDeleteCounterparty,
  useDeleteParticipant,
  useDeleteStore,
  useParticipants,
  useStores,
  useUpdateCounterparty,
  useUpdateParticipant,
  useUpdateStore,
} from "@/hooks/useDirectories";
import { UnitsCard } from "@/components/directories/UnitsCard";
import { useConfirm } from "@/components/ui/ConfirmProvider";
import { formatCurrency } from "@/lib/format";
import { useTranslation, type TranslationKey } from "@/lib/i18n";

interface Entry {
  id: number;
  name: string;
  is_archived: boolean;
  /** Сколько операций ссылается на запись. */
  usage: number;
  /** Сколько денег ушло в эту запись — есть только у магазинов. */
  spent_total?: number | string;
  spent_year?: number | string;
}

/**
 * Справочники: люди, контрагенты, магазины.
 *
 * Появились потому, что переименовать было нечем. Имя человека
 * подставлено в сотни строк операций, но хранится один раз — операции
 * ссылаются на запись по номеру. Значит, исправление опечатки в одном
 * месте исправляет её везде разом; без этой страницы такой правки не
 * существовало вовсе.
 *
 * Архив и удаление — разные действия, и оба нужны. Архив убирает запись
 * из выпадающих списков, оставляя её в прошлых операциях: так поступают с
 * магазином, куда перестали ходить. Удаление стирает запись совсем, а
 * ссылки на неё обнуляются — операции остаются, поле у них пустеет; так
 * поступают с записью, заведённой по ошибке.
 *
 * Рядом с именем стоит число операций, которые на него ссылаются. Без
 * него удаление вслепую: «Магазин у дома» и «Магазин у дома ` с опечаткой выглядят
 * в списке одинаково, а стоят за ними триста покупок и ноль.
 */
export function DirectoriesPage() {
  const { t } = useTranslation();
  const [showArchived, setShowArchived] = useState(false);

  const participants = useParticipants(showArchived);
  const counterparties = useCounterparties(showArchived);
  const stores = useStores(showArchived);

  const createParticipant = useCreateParticipant();
  const createCounterparty = useCreateCounterparty();
  const createStore = useCreateStore();
  const updateParticipant = useUpdateParticipant();
  const updateCounterparty = useUpdateCounterparty();
  const updateStore = useUpdateStore();
  const deleteParticipant = useDeleteParticipant();
  const deleteCounterparty = useDeleteCounterparty();
  const deleteStore = useDeleteStore();

  return (
    <div className="space-y-5">
      <div className="flex justify-end">
        <label className="flex cursor-pointer items-center gap-2 text-sm text-text-secondary">
          <input
            type="checkbox"
            checked={showArchived}
            onChange={(event) => setShowArchived(event.target.checked)}
            className="h-3.5 w-3.5 accent-text-primary"
          />
          {t("directories.showArchived")}
        </label>
      </div>

      <DirectorySection
        titleKey="directories.people"
        hintKey="directories.peopleHint"
        entries={participants.data ?? []}
        isLoading={participants.isLoading}
        onCreate={async (name) => void (await createParticipant.mutateAsync({ name }))}
        onRename={async (id, name) => void (await updateParticipant.mutateAsync({ id, input: { name } }))}
        onArchive={async (id, archived) =>
          void (await updateParticipant.mutateAsync({ id, input: { is_archived: archived } }))
        }
        onDelete={async (id) => void (await deleteParticipant.mutateAsync(id))}
      />

      <DirectorySection
        titleKey="directories.counterparties"
        hintKey="directories.counterpartiesHint"
        entries={counterparties.data ?? []}
        isLoading={counterparties.isLoading}
        onCreate={async (name) => void (await createCounterparty.mutateAsync({ name }))}
        onRename={async (id, name) => void (await updateCounterparty.mutateAsync({ id, input: { name } }))}
        onArchive={async (id, archived) =>
          void (await updateCounterparty.mutateAsync({ id, input: { is_archived: archived } }))
        }
        onDelete={async (id) => void (await deleteCounterparty.mutateAsync(id))}
      />

      <DirectorySection
        titleKey="directories.stores"
        hintKey="directories.storesHint"
        entries={stores.data ?? []}
        isLoading={stores.isLoading}
        onCreate={async (name) => void (await createStore.mutateAsync({ name }))}
        onRename={async (id, name) => void (await updateStore.mutateAsync({ id, input: { name } }))}
        onArchive={async (id, archived) =>
          void (await updateStore.mutateAsync({ id, input: { is_archived: archived } }))
        }
        onDelete={async (id) => void (await deleteStore.mutateAsync(id))}
      />

      <UnitsCard />
    </div>
  );
}

interface DirectorySectionProps {
  titleKey: TranslationKey;
  hintKey: TranslationKey;
  entries: Entry[];
  isLoading: boolean;
  onCreate: (name: string) => Promise<void>;
  onRename: (id: number, name: string) => Promise<void>;
  onArchive: (id: number, archived: boolean) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
}

/** Три справочника устроены одинаково — одна карточка на все три, а не
 *  три почти одинаковые копии, которые разойдутся при первой правке. */
function DirectorySection({
  titleKey,
  hintKey,
  entries,
  isLoading,
  onCreate,
  onRename,
  onArchive,
  onDelete,
}: DirectorySectionProps) {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const [adding, setAdding] = useState(false);
  const [newName, setNewName] = useState("");

  async function commitRename(id: number) {
    const trimmed = draft.trim();
    if (trimmed) await onRename(id, trimmed);
    setEditingId(null);
  }

  async function commitCreate() {
    const trimmed = newName.trim();
    if (!trimmed) return;
    await onCreate(trimmed);
    setNewName("");
    setAdding(false);
  }

  return (
    <Card>
      <CardHeader className="items-start">
        <div className="flex items-center gap-2">
          <CardTitle>{t(titleKey)}</CardTitle>
          <HelpBadge hintKey={hintKey} />
        </div>
        <Button variant="secondary" onClick={() => setAdding(true)}>
          <Plus size={16} />
          {t("common.add")}
        </Button>
      </CardHeader>
      <CardContent>
        {adding && (
          <div className="mb-3 flex gap-1.5">
            <Input
              value={newName}
              onChange={(event) => setNewName(event.target.value)}
              placeholder={t("directories.namePlaceholder")}
              autoFocus
              onKeyDown={(event) => {
                if (event.key === "Enter") void commitCreate();
                if (event.key === "Escape") {
                  setAdding(false);
                  setNewName("");
                }
              }}
            />
            <button
              type="button"
              onClick={() => void commitCreate()}
              aria-label={t("common.save")}
              className="shrink-0 rounded-lg border border-border px-2 text-text-muted hover:bg-surface-2 hover:text-text-primary"
            >
              <Check size={15} />
            </button>
            <button
              type="button"
              onClick={() => {
                setAdding(false);
                setNewName("");
              }}
              aria-label={t("common.cancel")}
              className="shrink-0 rounded-lg border border-border px-2 text-text-muted hover:bg-surface-2 hover:text-text-primary"
            >
              <X size={15} />
            </button>
          </div>
        )}

        {isLoading ? (
          <p className="py-6 text-center text-sm text-text-muted">{t("common.loading")}</p>
        ) : entries.length === 0 ? (
          <p className="py-6 text-center text-sm text-text-muted">{t("directories.empty")}</p>
        ) : (
          <ul className="divide-y divide-gridline">
            {entries.map((entry) => (
              <li key={entry.id} className="flex items-center gap-2 py-2">
                {editingId === entry.id ? (
                  <>
                    <Input
                      value={draft}
                      onChange={(event) => setDraft(event.target.value)}
                      autoFocus
                      onKeyDown={(event) => {
                        if (event.key === "Enter") void commitRename(entry.id);
                        if (event.key === "Escape") setEditingId(null);
                      }}
                    />
                    <button
                      type="button"
                      onClick={() => void commitRename(entry.id)}
                      aria-label={t("common.save")}
                      className="shrink-0 rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
                    >
                      <Check size={15} />
                    </button>
                    <button
                      type="button"
                      onClick={() => setEditingId(null)}
                      aria-label={t("common.cancel")}
                      className="shrink-0 rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
                    >
                      <X size={15} />
                    </button>
                  </>
                ) : (
                  <>
                    <span
                      className={`min-w-0 flex-1 truncate text-sm ${
                        entry.is_archived ? "text-text-muted line-through" : "text-text-primary"
                      }`}
                    >
                      {entry.name}
                      {entry.usage > 0 && (
                        <span className="ml-2 text-xs text-text-muted">
                          {t("directories.usage", { count: entry.usage })}
                        </span>
                      )}
                      {/* Потрачено — под именем, а не рядом: на телефоне
                          сумма в одну строку с названием магазина
                          вытесняет само название. */}
                      {Number(entry.spent_total ?? 0) > 0 && (
                        <span className="mt-0.5 block text-xs tabular-nums text-text-muted">
                          {t("directories.spent", { total: formatCurrency(entry.spent_total ?? 0) })}
                          {Number(entry.spent_year ?? 0) > 0 &&
                            ` · ${t("directories.spentYear", { year: formatCurrency(entry.spent_year ?? 0) })}`}
                        </span>
                      )}
                    </span>
                    <button
                      type="button"
                      onClick={() => {
                        setEditingId(entry.id);
                        setDraft(entry.name);
                      }}
                      aria-label={t("common.edit")}
                      title={t("directories.renameHint")}
                      className="shrink-0 rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
                    >
                      <Pencil size={15} />
                    </button>
                    <button
                      type="button"
                      onClick={() => void onArchive(entry.id, !entry.is_archived)}
                      aria-label={entry.is_archived ? t("directories.restore") : t("directories.archive")}
                      title={entry.is_archived ? t("directories.restore") : t("directories.archive")}
                      className="shrink-0 rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
                    >
                      {entry.is_archived ? <ArchiveRestore size={15} /> : <Archive size={15} />}
                    </button>
                    <button
                      type="button"
                      onClick={async () => {
                        // Число операций показывается до удаления, а не
                        // после: «Магазин у дома» и «Магазин у дома ` с опечаткой в
                        // списке выглядят одинаково, а стоят за ними
                        // триста покупок и ноль.
                        const ok = await confirm({
                          message:
                            entry.usage > 0
                              ? t("directories.confirmDeleteUsed", {
                                  name: entry.name,
                                  count: entry.usage,
                                })
                              : t("directories.confirmDelete", { name: entry.name }),
                          confirmLabel: t("common.delete"),
                          tone: "danger",
                        });
                        if (ok) await onDelete(entry.id);
                      }}
                      aria-label={t("common.delete")}
                      title={t("common.delete")}
                      className="shrink-0 rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-danger"
                    >
                      <Trash2 size={15} />
                    </button>
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
