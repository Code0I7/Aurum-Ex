import { useState } from "react";
import { Combobox } from "@/components/ui/Combobox";
import { Input, Label } from "@/components/ui/Input";
import { getMonthLabels } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import {
  describeRecurrence,
  nthLabels,
  presetOf,
  recurrenceOfPreset,
  stepUnitLabel,
  weekdayLabels,
  type Recurrence,
  type RecurrencePreset,
} from "@/lib/recurrence";
import type { PlanFrequency, PlanMonthDayMode } from "@/types";

interface RecurrenceEditorProps {
  value: Recurrence;
  onChange: (next: Recurrence) => void;
}

const PRESET_KEYS: Record<RecurrencePreset, string> = {
  once: "planning.repeat.once",
  daily: "planning.repeat.daily",
  workday: "planning.repeat.workday",
  weekly: "planning.repeat.weekly",
  monthly: "planning.repeat.monthly",
  yearly: "planning.repeat.yearly",
  custom: "planning.repeat.custom",
};

const MONTH_DAY_KEYS: Record<string, string> = {
  any: "planning.monthDay.any",
  day_of_month: "planning.monthDay.dayOfMonth",
  nth_weekday: "planning.monthDay.nthWeekday",
  last_day: "planning.monthDay.lastDay",
  first_workday: "planning.monthDay.firstWorkday",
  last_workday: "planning.monthDay.lastWorkday",
};

/**
 * Редактор расписания: «когда» у плана.
 *
 * Сверху готовые варианты, ниже — только те уточнения, которые при этом
 * варианте что-то значат. Показывать все семь полей сразу нельзя: дни
 * недели у годового плана и месяцы у недельного сервер не примет, и форма,
 * позволяющая их выбрать, обещает несуществующее.
 *
 * Под всем — одна строка словами. Семь полей человек в голове не собирает,
 * а под ними стоит сумма, и «каждые 2 недели по понедельникам» — это то,
 * что он обязан прочитать, прежде чем поверить числу в таблице года.
 *
 * Лежит отдельным файлом, а не внутри формы плана: правило уже больше
 * остальной формы, и растворить его в ней значило бы получить экран, где
 * категория и сумма теряются среди галочек.
 */
export function RecurrenceEditor({ value, onChange }: RecurrenceEditorProps) {
  const { t, language } = useTranslation();
  // «Произвольно» держится своим состоянием, а не вычисляется из правила:
  // шаг в единицу — это то же самое, что «ежедневно», и выведенный пресет
  // выбрасывал бы человека из произвольного режима ровно в тот момент,
  // когда он стирает число, чтобы напечатать другое.
  const [custom, setCustom] = useState(presetOf(value) === "custom");
  const preset = custom ? "custom" : presetOf(value);
  const weekdays = weekdayLabels(language);
  const months = getMonthLabels(language);

  function patch(changes: Partial<Recurrence>) {
    onChange({ ...value, ...changes });
  }

  function toggle(list: number[] | null, item: number): number[] | null {
    const current = list ?? [];
    const next = current.includes(item)
      ? current.filter((entry) => entry !== item)
      : [...current, item];
    // Пустой список означает «не задано», а не «ничего»: сервер в таком
    // случае берёт день из даты начала, и это честнее, чем план, который
    // не наступает никогда.
    return next.length > 0 ? next.sort((left, right) => left - right) : null;
  }

  const isCustom = preset === "custom";
  const showWeekdays = value.kind === "week";
  const showMonthDay = value.kind === "month" || value.kind === "year";
  const showMonths = value.kind === "year";

  return (
    <div className="space-y-3 rounded-lg border border-border p-3">
      <div>
        <Label htmlFor="plan-repeat">{t("planning.repeat")}</Label>
        <Combobox
          id="plan-repeat"
          className="mt-1"
          options={(Object.keys(PRESET_KEYS) as RecurrencePreset[]).map((key) => ({
            value: key,
            label: t(PRESET_KEYS[key] as never),
          }))}
          value={preset}
          onChange={(next) => {
            setCustom(next === "custom");
            onChange(recurrenceOfPreset(next as RecurrencePreset, value));
          }}
          placeholder={t("planning.repeat.monthly")}
        />
      </div>

      {/* Шаг спрашивается только у «произвольно»: у готовых вариантов он
          единица по определению, и поле с намертво стоящей единицей
          заставляло бы гадать, зачем оно. */}
      {isCustom && (
        <div className="grid grid-cols-[5rem_1fr] items-end gap-2">
          <div>
            <Label htmlFor="plan-step">{t("planning.repeatEvery")}</Label>
            <Input
              id="plan-step"
              type="number"
              min="1"
              max="365"
              value={String(value.repeat_every)}
              onChange={(event) =>
                patch({ repeat_every: Math.min(Math.max(Number(event.target.value) || 1, 1), 365) })
              }
            />
          </div>
          <Combobox
            options={(["day", "week", "month", "year"] as PlanFrequency[]).map((kind) => ({
              value: kind,
              label: stepUnitLabel(kind, value.repeat_every, language),
            }))}
            value={value.kind === "one_off" ? "month" : value.kind}
            onChange={(next) =>
              // Смена частоты обнуляет уточнения предыдущей: дни недели в
              // месячном плане ничего не значат, и сервер их не примет.
              onChange({
                ...recurrenceOfPreset(
                  next === "day"
                    ? "daily"
                    : next === "week"
                      ? "weekly"
                      : next === "month"
                        ? "monthly"
                        : "yearly",
                  value
                ),
                repeat_every: value.repeat_every,
              })
            }
            placeholder={stepUnitLabel("month", value.repeat_every, language)}
          />
        </div>
      )}

      {value.kind === "day" && isCustom && (
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            checked={value.skip_weekends}
            onChange={(event) =>
              patch({
                skip_weekends: event.target.checked,
                workdays_only: event.target.checked ? false : value.workdays_only,
              })
            }
            className="mt-0.5 h-3.5 w-3.5 accent-text-primary"
          />
          <span>{t("planning.skipWeekends")}</span>
        </label>
      )}

      {showWeekdays && (
        <div>
          <Label>{t("planning.onWeekdays")}</Label>
          <Chips
            className="mt-1"
            options={weekdays.map((label, index) => ({ value: index, label }))}
            selected={value.weekdays}
            onToggle={(day) => patch({ weekdays: toggle(value.weekdays, day) })}
          />
          <p className="mt-1 text-xs text-text-muted">{t("planning.onWeekdaysHint")}</p>
        </div>
      )}

      {showMonths && (
        <div>
          <Label>{t("planning.inMonths")}</Label>
          <Chips
            className="mt-1"
            options={months.map((label, index) => ({ value: index + 1, label }))}
            selected={value.months}
            onToggle={(month) => patch({ months: toggle(value.months, month) })}
          />
        </div>
      )}

      {showMonthDay && (
        <div>
          <Label htmlFor="plan-month-day">{t("planning.monthDayMode")}</Label>
          <Combobox
            id="plan-month-day"
            className="mt-1"
            options={Object.keys(MONTH_DAY_KEYS).map((key) => ({
              value: key,
              label: t(MONTH_DAY_KEYS[key] as never),
            }))}
            value={value.month_day_mode ?? "any"}
            onChange={(next) =>
              patch({
                month_day_mode: next === "any" ? null : (next as PlanMonthDayMode),
                // Числа и номер дня недели принадлежат разным режимам:
                // оставленные от предыдущего, они уедут на сервер и
                // вернутся ошибкой про поле, которого уже не видно.
                month_days: next === "day_of_month" ? value.month_days : null,
                nth_weekday: next === "nth_weekday" ? (value.nth_weekday ?? 1) : null,
                weekdays: next === "nth_weekday" ? value.weekdays : null,
              })
            }
            placeholder={t("planning.monthDay.any")}
          />
        </div>
      )}

      {showMonthDay && value.month_day_mode === "day_of_month" && (
        <div>
          <Label>{t("planning.monthDays")}</Label>
          <Chips
            className="mt-1"
            options={Array.from({ length: 28 }, (_, index) => ({
              value: index + 1,
              label: String(index + 1),
            }))}
            selected={value.month_days}
            onToggle={(day) => patch({ month_days: toggle(value.month_days, day) })}
          />
          <p className="mt-1 text-xs text-text-muted">{t("planning.monthDaysHint")}</p>
        </div>
      )}

      {showMonthDay && value.month_day_mode === "nth_weekday" && (
        <div className="space-y-2">
          <div>
            <Label htmlFor="plan-nth">{t("planning.nth")}</Label>
            <Combobox
              id="plan-nth"
              className="mt-1"
              // Род порядкового числительного зависит от дня недели: «первый
              // понедельник», но «первую среду». Берём первый выбранный.
              options={nthLabels(language, value.weekdays?.[0] ?? 0).map((option) => ({
                value: String(option.value),
                label: option.label,
              }))}
              value={String(value.nth_weekday ?? 1)}
              onChange={(next) => patch({ nth_weekday: Number(next) })}
              placeholder={nthLabels(language, 0)[0].label}
            />
          </div>
          <div>
            <Label>{t("planning.onWeekdays")}</Label>
            <Chips
              className="mt-1"
              options={weekdays.map((label, index) => ({ value: index, label }))}
              selected={value.weekdays}
              onToggle={(day) => patch({ weekdays: toggle(value.weekdays, day) })}
            />
          </div>
        </div>
      )}

      {/* Правило словами. Единственная строка, по которой видно, что
          получилось из всех полей выше. */}
      <p className="text-sm text-text-secondary">{describeRecurrence(value, language)}</p>
    </div>
  );
}

/**
 * Ряд переключателей-кнопок: дни недели, числа, месяцы.
 *
 * Кнопками, а не списком с множественным выбором: вариантов мало, они
 * короткие, и выбранное должно быть видно целиком без раскрытия — «по
 * понедельникам и средам» человек проверяет глазами, а не memory.
 */
function Chips({
  options,
  selected,
  onToggle,
  className = "",
}: {
  options: { value: number; label: string }[];
  selected: number[] | null;
  onToggle: (value: number) => void;
  className?: string;
}) {
  const active = new Set(selected ?? []);
  return (
    <div className={`flex flex-wrap gap-1 ${className}`}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          onClick={() => onToggle(option.value)}
          className={`min-w-[2.25rem] rounded-md border px-2 py-1 text-xs tabular-nums transition-colors ${
            active.has(option.value)
              ? "border-accent bg-accent/15 text-text-primary"
              : "border-border text-text-muted hover:bg-surface-2 hover:text-text-primary"
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
