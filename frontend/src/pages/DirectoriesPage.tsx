import { useState } from "react";
import { Archive, ArchiveRestore, Check, Pencil, Plus, X } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { HelpBadge } from "@/components/ui/HelpBadge";
import {
  useCounterparties,
  useCreateCounterparty,
  useCreateParticipant,
  useCreateStore,
  useParticipants,
  useStores,
  useUpdateCounterparty,
  useUpdateParticipant,
  useUpdateStore,
} from "@/hooks/useDirectories";
import { useTranslation, type TranslationKey } from "@/lib/i18n";

interface Entry {
  id: number;
  name: string;
  is_archived: boolean;
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
 * Удаления нет намеренно, только архив. Запись, на которую ссылаются
 * операции, нельзя убрать, не переписав историю: удалив «Ольгу», мы
 * получим полсотни операций, про которые больше нельзя сказать, на кого
 * они пришлись. Архив убирает имя из выпадающих списков и оставляет его в
 * прошлом.
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
      />
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
}: DirectorySectionProps) {
  const { t } = useTranslation();
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
