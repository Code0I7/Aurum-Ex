import { useState } from "react";
import { Check, Plus, Star, Trash2, X } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/Input";
import { HelpBadge } from "@/components/ui/HelpBadge";
import { useConfirm } from "@/components/ui/ConfirmProvider";
import { useCreateUnit, useDeleteUnit, useUpdateUnit } from "@/hooks/useDirectories";
import { useUnits } from "@/hooks/useProducts";
import { useTranslation } from "@/lib/i18n";
import type { Unit, UnitKind } from "@/types";

const KINDS: UnitKind[] = ["weight", "volume", "count", "length", "service"];

/**
 * Единицы измерения с коэффициентом к базовой мере своего вида.
 *
 * Коэффициент — весь смысл справочника. Без него «1,5 л сока за 120 ₽» и
 * «500 мл сока за 55 ₽» несравнимы, и отслеживание цен вырождается в
 * догадки: в исходной таблице колонки количества пустовали в 89% записей
 * именно потому, что её единицы (Шт, Опл, Бут, Уп, Кг, Л) были подписями
 * без арифметики.
 *
 * Базовую единицу вида удалить нельзя: без неё не к чему приводить
 * остальные, и вся история цен по этому виду рассыпается.
 */
export function UnitsCard() {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const { data: units, isLoading } = useUnits();
  const createUnit = useCreateUnit();
  const updateUnit = useUpdateUnit();
  const deleteUnit = useDeleteUnit();

  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState({ name: "", kind: "weight" as UnitKind, factor: "1" });
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState({ name: "", factor: "" });

  async function commitCreate() {
    const name = draft.name.trim();
    if (!name || Number(draft.factor) <= 0) return;
    await createUnit.mutateAsync({ name, kind: draft.kind, factor: draft.factor });
    setDraft({ name: "", kind: "weight", factor: "1" });
    setAdding(false);
  }

  async function commitEdit(unit: Unit) {
    const name = editDraft.name.trim();
    if (!name || Number(editDraft.factor) <= 0) return;
    await updateUnit.mutateAsync({ id: unit.id, input: { name, factor: editDraft.factor } });
    setEditingId(null);
  }

  return (
    <Card>
      <CardHeader className="items-start">
        <div className="flex items-center gap-2">
          <CardTitle>{t("directories.units")}</CardTitle>
          <HelpBadge hintKey="directories.unitsHint" />
        </div>
        <Button variant="secondary" onClick={() => setAdding(true)}>
          <Plus size={16} />
          {t("common.add")}
        </Button>
      </CardHeader>
      <CardContent>
        {adding && (
          <div className="mb-3 grid gap-1.5 sm:grid-cols-[1fr_1fr_1fr_auto_auto]">
            <Input
              value={draft.name}
              onChange={(event) => setDraft((prev) => ({ ...prev, name: event.target.value }))}
              placeholder={t("directories.unitName")}
              autoFocus
            />
            <Select
              value={draft.kind}
              onChange={(event) => setDraft((prev) => ({ ...prev, kind: event.target.value as UnitKind }))}
            >
              {KINDS.map((kind) => (
                <option key={kind} value={kind}>
                  {t(`directories.unitKind.${kind}` as never)}
                </option>
              ))}
            </Select>
            <Input
              type="number"
              step="0.000001"
              min="0"
              value={draft.factor}
              onChange={(event) => setDraft((prev) => ({ ...prev, factor: event.target.value }))}
              placeholder={t("directories.unitFactor")}
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
              onClick={() => setAdding(false)}
              aria-label={t("common.cancel")}
              className="shrink-0 rounded-lg border border-border px-2 text-text-muted hover:bg-surface-2 hover:text-text-primary"
            >
              <X size={15} />
            </button>
          </div>
        )}

        {isLoading ? (
          <p className="py-6 text-center text-sm text-text-muted">{t("common.loading")}</p>
        ) : (
          <ul className="divide-y divide-gridline">
            {(units ?? []).map((unit) => (
              <li key={unit.id} className="flex items-center gap-2 py-2">
                {editingId === unit.id ? (
                  <>
                    <Input
                      value={editDraft.name}
                      onChange={(event) => setEditDraft((prev) => ({ ...prev, name: event.target.value }))}
                      autoFocus
                    />
                    <Input
                      type="number"
                      step="0.000001"
                      min="0"
                      value={editDraft.factor}
                      onChange={(event) => setEditDraft((prev) => ({ ...prev, factor: event.target.value }))}
                    />
                    <button
                      type="button"
                      onClick={() => void commitEdit(unit)}
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
                    <button
                      type="button"
                      onClick={() => {
                        setEditingId(unit.id);
                        setEditDraft({ name: unit.name, factor: String(unit.factor) });
                      }}
                      className="min-w-0 flex-1 truncate text-left text-sm text-text-primary hover:underline"
                    >
                      {unit.name}
                      <span className="ml-2 text-xs text-text-muted">
                        {t(`directories.unitKind.${unit.kind}` as never)}
                        {/* Базовая подписана явно: она и есть та мера, к
                            которой приводятся остальные, и коэффициент 1 у
                            неё не совпадение. */}
                        {unit.is_base
                          ? ` · ${t("directories.unitBase")}`
                          : ` · ${t("directories.unitEquals", { factor: unit.factor })}`}
                      </span>
                    </button>
                    {/* Назначить базовой можно любую: «удобно сравнивать» —
                        вопрос привычки, а не физики. Кто-то считает бензин
                        литрами, кто-то заправками. */}
                    {!unit.is_base && (
                      <button
                        type="button"
                        onClick={() => updateUnit.mutate({ id: unit.id, input: { is_base: true } })}
                        aria-label={t("directories.makeBase")}
                        title={t("directories.makeBase")}
                        className="shrink-0 rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-accent"
                      >
                        <Star size={15} />
                      </button>
                    )}
                    {/* Удалить можно любую, включая базовую: признак базовой —
                        только подпись, в каких единицах выражена цена, а сам
                        расчёт идёт из коэффициента самой единицы. */}
                    <button
                      type="button"
                      onClick={async () => {
                        const ok = await confirm({
                          message: unit.is_base
                            ? t("directories.confirmDeleteBaseUnit", { name: unit.name })
                            : t("directories.confirmDeleteUnit", { name: unit.name }),
                          confirmLabel: t("common.delete"),
                          tone: "danger",
                        });
                        if (ok) await deleteUnit.mutateAsync(unit.id);
                      }}
                      aria-label={t("common.delete")}
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
