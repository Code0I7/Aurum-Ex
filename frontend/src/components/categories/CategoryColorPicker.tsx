import { useState } from "react";
import { Palette } from "lucide-react";
import { ColorHive } from "@/components/ui/ColorHive";
import { useTranslation } from "@/lib/i18n";
import { cn } from "@/lib/utils";

interface CategoryColorPickerProps {
  value: string;
  onChange: (color: string) => void;
}

// The same 8-slot colorblind-safe categorical palette the seeded default
// categories and every chart in the app already use — see
// backend/app/db/seed.py and index.css's --series-* tokens.
//
// Теперь их больше и они разложены по кругу оттенков: красные, оранжевые,
// жёлтые, зелёные, бирюзовые, синие, фиолетовые, розовые — и в конце
// нейтральные.
//
// Порядок не косметика. Раньше восемь цветов лежали в том порядке, в каком
// их назначает график: синий, оранжевый, зелёный, жёлтый вперемешку. Для
// графика это правильно — соседние ряды должны различаться. Для выбора
// цвета категории нет: человек ищет «что-нибудь зелёное», а не «третий по
// счёту», и перебирает список глазами до конца.
//
// Добавленные — пары «насыщенный и светлый» у каждого оттенка: соседние
// ветки дерева так разводятся, не меняя цвета.
const PRESET_COLORS = [
  "#e34948",
  "#f08a8a",
  "#eb6834",
  "#f0a878",
  "#eda100",
  "#f2cc66",
  "#008300",
  "#1baf7a",
  "#7fd4b4",
  "#199e9e",
  "#2a78d6",
  "#7fb0e8",
  "#4a3aa7",
  "#8f83cf",
  "#a44ab5",
  "#e87ba4",
  "#8a6a4f",
  "#898781",
];

export function CategoryColorPicker({ value, onChange }: CategoryColorPickerProps) {
  const { t } = useTranslation();
  const normalized = value.toLowerCase();
  // Соты свёрнуты по умолчанию: в девяти случаях из десяти цвет берут из
  // готовых, а раскрытый виджет занимает полкарточки.
  const [hiveOpen, setHiveOpen] = useState(false);
  const isCustom = !PRESET_COLORS.includes(normalized);

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        {PRESET_COLORS.map((color) => (
          <button
            key={color}
            type="button"
            aria-label={color}
            aria-pressed={normalized === color}
            onClick={() => onChange(color)}
            className={cn(
              "h-7 w-7 rounded-full border-2 transition-transform",
              normalized === color ? "scale-110 border-text-primary" : "border-transparent hover:scale-105"
            )}
            style={{ backgroundColor: color }}
          />
        ))}

        {/* Кнопка своего цвета залита выбранным, когда он не из палитры:
            иначе непонятно, что вообще выбрано. */}
        <button
          type="button"
          aria-expanded={hiveOpen}
          aria-label={t("category.form.customColorLabel")}
          title={t("category.form.customColorLabel")}
          onClick={() => setHiveOpen((open) => !open)}
          className={cn(
            "flex h-7 w-7 items-center justify-center rounded-md border-2 transition-transform",
            hiveOpen || isCustom ? "border-text-primary" : "border-border hover:scale-105"
          )}
          style={isCustom ? { backgroundColor: value } : undefined}
        >
          <Palette size={14} className={isCustom ? "text-surface-0" : "text-text-muted"} />
        </button>
      </div>

      {hiveOpen && (
        <div className="rounded-lg border border-border bg-surface-1 p-3">
          <ColorHive value={value} onChange={onChange} />
        </div>
      )}
    </div>
  );
}
