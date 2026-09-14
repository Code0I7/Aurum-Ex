import { useLocation } from "react-router-dom";
import { Menu } from "lucide-react";
import { NAV_ITEMS } from "@/lib/navigation";
import { PageActionsOutlet } from "@/components/layout/PageActions";
import { HelpBadge } from "@/components/ui/HelpBadge";
import { useTranslation } from "@/lib/i18n";

interface TopbarProps {
  onOpenMobileNav: () => void;
}

export function Topbar({ onOpenMobileNav }: TopbarProps) {
  const location = useLocation();
  const { t } = useTranslation();
  const activeItem = NAV_ITEMS.find((item) => (item.to === "/" ? location.pathname === "/" : location.pathname.startsWith(item.to)));

  return (
    <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-border bg-surface-0/95 px-4 py-3.5 backdrop-blur sm:px-6 lg:px-8">
      <button
        type="button"
        onClick={onOpenMobileNav}
        aria-label={t("topbar.openMenu")}
        className="rounded-md p-1.5 text-text-secondary hover:bg-surface-2 lg:hidden"
      >
        <Menu size={20} />
      </button>
      {/* Обрезается только название, а не весь заголовок. Обрезка — это
          overflow: hidden, и стояла она на h1 вместе с кружком «!»: кружок
          нажимался, подсказка открывалась — и тут же отрезалась краем
          заголовка. Со стороны это выглядело как кнопка, которая не
          нажимается. */}
      <h1 className="flex min-w-0 items-center gap-2 text-lg font-semibold text-text-primary">
        <span className="truncate">{activeItem ? t(activeItem.labelKey) : "Aurum-Ex"}</span>
        {/* Место для объяснения одно на всё приложение — у названия
            вкладки. Разделы, где пояснять нечего, кружка просто не имеют, и
            заголовок от этого не съезжает. */}
        {activeItem?.hintKey && <HelpBadge hintKey={activeItem.hintKey} />}
      </h1>

      {/* Главное действие вкладки. Шапка прилипшая, поэтому кнопка
          доступна на любой глубине списка — см. PageActions. */}
      <PageActionsOutlet className="ml-auto flex shrink-0 items-center gap-2" />
    </header>
  );
}
