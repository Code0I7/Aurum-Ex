import { useEffect } from "react";
import { NavLink } from "react-router-dom";
import { PanelLeftClose, PanelLeftOpen, X } from "lucide-react";
import { Logo } from "@/components/layout/Logo";
import { NAV_ITEMS } from "@/lib/navigation";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/lib/i18n";

interface NavListProps {
  collapsed: boolean;
  onNavigate?: () => void;
}

function NavList({ collapsed, onNavigate }: NavListProps) {
  const { t } = useTranslation();

  return (
    <nav className="flex flex-1 flex-col gap-0.5 overflow-y-auto px-2.5 py-2">
      {NAV_ITEMS.map((item) => {
        const Icon = item.icon;
        const label = t(item.labelKey);
        if (item.disabled) {
          return (
            <span
              key={item.to}
              title={collapsed ? `${label} (${t("nav.comingSoon")})` : undefined}
              className={cn(
                "flex cursor-not-allowed items-center gap-3 rounded-lg px-2.5 py-2 text-sm text-text-muted",
                collapsed && "justify-center px-0"
              )}
            >
              <Icon size={18} className="shrink-0" />
              {!collapsed && (
                <span className="flex min-w-0 flex-1 items-center justify-between gap-2">
                  <span className="truncate">{label}</span>
                  <span className="shrink-0 rounded bg-surface-2 px-1 py-0.5 text-[10px] leading-none">
                    {t("nav.comingSoon")}
                  </span>
                </span>
              )}
            </span>
          );
        }

        return (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            onClick={onNavigate}
            title={collapsed ? label : undefined}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-lg px-2.5 py-2 text-sm font-medium text-text-secondary transition-colors hover:bg-surface-2 hover:text-text-primary",
                collapsed && "justify-center px-0",
                isActive && "bg-surface-2 text-text-primary"
              )
            }
          >
            <Icon size={18} className="shrink-0" />
            {!collapsed && <span className="truncate">{label}</span>}
          </NavLink>
        );
      })}
    </nav>
  );
}

interface SidebarProps {
  collapsed: boolean;
  onToggleCollapsed: () => void;
  mobileOpen: boolean;
  onCloseMobile: () => void;
}

export function Sidebar({ collapsed, onToggleCollapsed, mobileOpen, onCloseMobile }: SidebarProps) {
  const { t } = useTranslation();

  useEffect(() => {
    if (!mobileOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCloseMobile();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [mobileOpen, onCloseMobile]);

  return (
    <>
      {/* Desktop: persistent rail, collapsible between icon-only and full width. */}
      <aside
        className={cn(
          "sticky top-0 hidden h-screen shrink-0 flex-col border-r border-border bg-surface-1 transition-[width] duration-150 lg:flex",
          collapsed ? "w-[72px]" : "w-56"
        )}
      >
        {collapsed ? (
          // Collapsed: the logo doubles as an "expand" button — the sidebar
          // has no visible label to click in this state, so the icon itself
          // needs to be the way back to the full menu.
          <button
            type="button"
            onClick={onToggleCollapsed}
            title={t("sidebar.expandMenu")}
            className="flex items-center justify-center gap-2 px-0 py-4 hover:opacity-80"
          >
            <Logo size={24} />
          </button>
        ) : (
          <div className="flex items-center gap-2 px-4 py-4">
            <Logo size={24} />
            <span className="text-lg font-semibold tracking-tight text-text-primary">Aurum</span>
          </div>
        )}
        <NavList collapsed={collapsed} />
        <div className="border-t border-border p-2.5">
          <button
            type="button"
            onClick={onToggleCollapsed}
            title={collapsed ? t("sidebar.expandMenu") : t("sidebar.collapseMenu")}
            className={cn(
              "flex w-full items-center gap-3 rounded-lg px-2.5 py-2 text-sm text-text-muted hover:bg-surface-2 hover:text-text-primary",
              collapsed && "justify-center px-0"
            )}
          >
            {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
            {!collapsed && <span>{t("sidebar.collapse")}</span>}
          </button>
        </div>
      </aside>

      {/* Mobile: off-canvas drawer over a backdrop. */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-black/40" onClick={onCloseMobile} />
          <aside className="absolute inset-y-0 left-0 flex w-64 flex-col bg-surface-1 shadow-xl">
            <div className="flex items-center justify-between gap-2 px-4 py-4">
              <span className="flex items-center gap-2 text-lg font-semibold tracking-tight text-text-primary">
                <Logo size={24} /> Aurum
              </span>
              <button
                type="button"
                onClick={onCloseMobile}
                aria-label={t("sidebar.closeMenu")}
                className="rounded-md p-1 text-text-muted hover:bg-surface-2"
              >
                <X size={18} />
              </button>
            </div>
            <NavList collapsed={false} onNavigate={onCloseMobile} />
          </aside>
        </div>
      )}
    </>
  );
}
