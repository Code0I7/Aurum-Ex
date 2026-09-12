import type {
  InputHTMLAttributes,
  LabelHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
} from "react";
import { HelpBadge } from "@/components/ui/HelpBadge";
import type { TranslationKey } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "h-9 w-full rounded-lg border border-border bg-surface-1 px-3 text-sm text-text-primary outline-none focus:border-series-1",
        className
      )}
      {...props}
    />
  );
}

export function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "h-9 w-full rounded-lg border border-border bg-surface-1 px-3 text-sm text-text-primary outline-none focus:border-series-1",
        className
      )}
      {...props}
    >
      {children}
    </select>
  );
}

export function Label({ className, ...props }: LabelHTMLAttributes<HTMLLabelElement>) {
  return <label className={cn("mb-1 block text-xs font-medium text-text-secondary", className)} {...props} />;
}

/**
 * Подпись поля со значком объяснения.
 *
 * Объяснение прячется в кружок, а не стоит абзацем под полем. В форме
 * операции таких абзацев было четыре, и вместе они занимали больше места,
 * чем сами поля: человек, заполнивший эту форму двести раз, читает их не с
 * первого раза, а ни одного.
 *
 * Значок стоит рядом с подписью, а НЕ внутри неё: щелчок по кнопке внутри
 * <label> заодно переключает поле, и у галочки это означало бы, что
 * объяснение её и включает.
 */
export function LabelWithHelp({
  htmlFor,
  hintKey,
  children,
}: {
  htmlFor?: string;
  hintKey: TranslationKey;
  children: ReactNode;
}) {
  return (
    <div className="mb-1 flex items-center gap-1.5">
      <Label htmlFor={htmlFor} className="mb-0">
        {children}
      </Label>
      <HelpBadge hintKey={hintKey} />
    </div>
  );
}
