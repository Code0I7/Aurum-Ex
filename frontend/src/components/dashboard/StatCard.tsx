import { Card } from "@/components/ui/Card";
import { HelpBadge } from "@/components/ui/HelpBadge";
import { cn } from "@/lib/utils";
import type { TranslationKey } from "@/lib/i18n";

interface StatCardProps {
  label: string;
  value: string;
  /**
   * Объяснение показателя — в подсказке у названия, а не строкой под
   * числом.
   *
   * Строкой оно занимало треть карточки и читалось один раз в жизни:
   * «что такое реальный доход» — вопрос, который задают однажды, а место
   * подпись отнимала в каждом просмотре. Пять карточек в ряд по три
   * строки каждая на телефоне вытесняли всё остальное за экран.
   */
  hintKey?: TranslationKey;
  /** Короткая подпись под числом: то, что меняется вместе с ним и потому
   *  не годится в подсказку — «за 164 ч работы». */
  caption?: string;
  tone?: "default" | "success" | "danger";
}

const TONE_CLASSES: Record<NonNullable<StatCardProps["tone"]>, string> = {
  default: "text-text-primary",
  success: "text-success",
  danger: "text-danger",
};

export function StatCard({ label, value, hintKey, caption, tone = "default" }: StatCardProps) {
  return (
    <Card className="p-4 sm:p-5">
      <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-text-muted">
        {label}
        {hintKey && <HelpBadge hintKey={hintKey} />}
      </p>
      <p className={cn("mt-1.5 text-2xl font-semibold tabular-nums sm:text-[28px]", TONE_CLASSES[tone])}>
        {value}
      </p>
      {caption && <p className="mt-1 text-xs text-text-muted">{caption}</p>}
    </Card>
  );
}
