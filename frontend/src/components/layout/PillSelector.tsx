import { cn } from "@/lib/utils";

interface PillOption<T extends string | number> {
  value: T;
  label: string;
}

interface PillSelectorProps<T extends string | number> {
  options: Array<PillOption<T>>;
  value: T;
  onChange: (value: T) => void;
}

export function PillSelector<T extends string | number>({ options, value, onChange }: PillSelectorProps<T>) {
  return (
    <div className="inline-flex gap-1 rounded-lg border border-border bg-surface-1 p-1">
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            className={cn(
              "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
              active ? "bg-surface-2 text-text-primary" : "text-text-muted hover:text-text-primary"
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
