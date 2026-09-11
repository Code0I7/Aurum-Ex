import { useMemo } from "react";
import { useTranslation } from "@/lib/i18n";

/**
 * Выбор произвольного цвета сотами.
 *
 * Заменяет `<input type="color">`. Тот открывает системное окно: на Windows
 * это диалог из девяностых с пипеткой и полями RGB, на телефоне — куцый
 * список из десятка квадратов. Выглядит оно везде по-разному, и мы на это
 * никак не влияем.
 *
 * Соты устроены так, как цвет и выбирают: угол задаёт оттенок, расстояние
 * от центра — насыщенность. В центре белое, к краю цвет набирает силу.
 * Внизу отдельная полоса серого от белого к чёрному: серый в круге оттенков
 * места не имеет — у него нет угла, — а нужен он ровно так же часто.
 */
interface ColorHiveProps {
  value: string;
  onChange: (color: string) => void;
}

/** Колец сот вокруг центра. Четыре даёт 61 ячейку: заметно больше палитры,
 *  но всё ещё помещается в ладонь на телефоне. */
const RINGS = 4;
/** Радиус ячейки в единицах SVG. Реальный размер задаёт CSS. */
const CELL = 10;
/** Насыщенность держим высокой: выцветшие оттенки даёт уже приближение к
 *  центру, и второй способ получить бледное только запутал бы. */
const SATURATION = 82;

interface Cell {
  key: string;
  points: string;
  color: string;
}

function hslToHex(h: number, s: number, l: number): string {
  const a = (s / 100) * Math.min(l / 100, 1 - l / 100);
  const channel = (n: number) => {
    const k = (n + h / 30) % 12;
    const value = l / 100 - a * Math.max(-1, Math.min(k - 3, 9 - k, 1));
    return Math.round(255 * value)
      .toString(16)
      .padStart(2, "0");
  };
  return `#${channel(0)}${channel(8)}${channel(4)}`;
}

/** Соты в осевых координатах: клетка (q, r) лежит в кольце
 *  (|q| + |r| + |q + r|) / 2 — это стандартное расстояние на шестиугольной
 *  сетке, и оно же служит насыщенностью. */
function buildCells(): Cell[] {
  const cells: Cell[] = [];
  const width = Math.sqrt(3) * CELL;

  for (let q = -RINGS; q <= RINGS; q += 1) {
    for (let r = -RINGS; r <= RINGS; r += 1) {
      const ring = (Math.abs(q) + Math.abs(r) + Math.abs(q + r)) / 2;
      if (ring > RINGS) continue;

      const x = width * (q + r / 2);
      const y = CELL * 1.5 * r;

      // Центр — чистый белый: угла у него нет, а оттенок без угла не
      // определён. Остальные берут оттенок из угла, светлоту — из кольца.
      const hue = (Math.atan2(y, x) * 180) / Math.PI;
      const lightness = 95 - (45 * ring) / RINGS;
      const color = ring === 0 ? "#ffffff" : hslToHex((hue + 360) % 360, SATURATION, lightness);

      const points = Array.from({ length: 6 }, (_, index) => {
        const angle = (Math.PI / 180) * (60 * index - 30);
        return `${(x + CELL * Math.cos(angle)).toFixed(2)},${(y + CELL * Math.sin(angle)).toFixed(2)}`;
      }).join(" ");

      cells.push({ key: `${q}:${r}`, points, color });
    }
  }
  return cells;
}

/** Полоса серого: белый, пять ступеней и чёрный. Ступени неравномерны
 *  намеренно — глаз различает светлые оттенки хуже тёмных, и равномерный
 *  шаг дал бы четыре почти одинаковых светлых квадрата. */
const GREYS = ["#ffffff", "#d4d4d4", "#a3a3a3", "#737373", "#4a4a4a", "#262626", "#000000"];

export function ColorHive({ value, onChange }: ColorHiveProps) {
  const { t } = useTranslation();
  const cells = useMemo(buildCells, []);
  const normalized = value.toLowerCase();

  const extent = Math.sqrt(3) * CELL * (RINGS + 0.5);
  const viewBox = `${-extent} ${-extent} ${extent * 2} ${extent * 2}`;

  return (
    <div className="space-y-2">
      <svg viewBox={viewBox} className="mx-auto block w-full max-w-[15rem]" role="group" aria-label={t("category.form.customColorLabel")}>
        {cells.map((cell) => (
          <polygon
            key={cell.key}
            points={cell.points}
            fill={cell.color}
            // Обводка выбранной ячейки рисуется изнутри: внешняя налезала бы
            // на соседние соты и смещала бы их на глаз.
            stroke={normalized === cell.color ? "var(--text-primary)" : "var(--surface-0)"}
            strokeWidth={normalized === cell.color ? 2.5 : 0.6}
            className="cursor-pointer"
            onClick={() => onChange(cell.color)}
          >
            <title>{cell.color}</title>
          </polygon>
        ))}
      </svg>

      <div className="flex justify-center gap-1">
        {GREYS.map((color) => (
          <button
            key={color}
            type="button"
            aria-label={color}
            aria-pressed={normalized === color}
            onClick={() => onChange(color)}
            className={`h-6 w-6 rounded-md border-2 transition-transform ${
              normalized === color ? "scale-110 border-text-primary" : "border-border hover:scale-105"
            }`}
            style={{ backgroundColor: color }}
          />
        ))}
      </div>
    </div>
  );
}
