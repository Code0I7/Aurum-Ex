import {
  Activity,
  ArrowLeftRight,
  Calculator,
  CalendarRange,
  CandlestickChart,
  Coins,
  Flag,
  HandCoins,
  Layers,
  LayoutDashboard,
  Lightbulb,
  PieChart,
  Repeat,
  Ruler,
  Settings,
  ShoppingBasket,
  Tags,
  Target,
  TrendingUp,
  Users,
  type LucideIcon,
} from "lucide-react";

import type { TranslationKey } from "@/lib/i18n";

export interface NavItem {
  labelKey: TranslationKey;
  to: string;
  icon: LucideIcon;
  disabled?: boolean;
  /** Объяснение раздела, показываемое кружком в шапке рядом с названием.
   *  Живёт здесь, а не на странице: место у заголовка одно на всё
   *  приложение, и подсказка обязана быть в нём всегда на одном месте. */
  hintKey?: TranslationKey;
}

export interface NavGroup {
  /** Пусто у первой группы: заголовок над «Обзором» ничего не добавляет. */
  labelKey: TranslationKey | null;
  items: NavItem[];
}

/**
 * Меню сгруппировано, а не выложено плоским списком.
 *
 * Пунктов стало восемнадцать, и плоский список такой длины перестаёт
 * читаться: глаз ищет нужное перебором сверху вниз каждый раз. Группы
 * отвечают на вопрос «в какой части приложения это живёт» до того, как
 * человек начнёт читать названия.
 *
 * Порядок внутри групп — от того, чем пользуются каждый день, к тому, что
 * открывают раз в месяц.
 */
export const NAV_GROUPS: NavGroup[] = [
  {
    labelKey: null,
    items: [
      { labelKey: "nav.dashboard", to: "/", icon: LayoutDashboard, hintKey: "help.dashboard" },
      { labelKey: "nav.transactions", to: "/transactions", icon: ArrowLeftRight, hintKey: "help.transactions" },
      { labelKey: "nav.accounts", to: "/accounts", icon: Layers, hintKey: "help.accounts" },
    ],
  },
  {
    labelKey: "nav.group.analysis",
    items: [
      { labelKey: "nav.cashFlow", to: "/cash-flow", icon: Activity, hintKey: "help.cashFlow" },
      { labelKey: "nav.reports", to: "/reports", icon: PieChart, hintKey: "help.reports" },
      { labelKey: "nav.netWorth", to: "/net-worth", icon: TrendingUp, hintKey: "help.netWorth" },
      { labelKey: "nav.advice", to: "/advice", icon: Lightbulb, hintKey: "help.advice" },
    ],
  },
  {
    labelKey: "nav.group.plans",
    items: [
      { labelKey: "nav.budget", to: "/budget", icon: Target, hintKey: "help.budget" },
      { labelKey: "nav.planning", to: "/planning", icon: CalendarRange, hintKey: "help.planning" },
      { labelKey: "nav.goals", to: "/goals", icon: Flag, hintKey: "help.goals" },
      { labelKey: "nav.recurring", to: "/recurring", icon: Repeat, hintKey: "help.recurring" },
      { labelKey: "nav.debts", to: "/debts", icon: HandCoins, hintKey: "help.debts" },
    ],
  },
  {
    labelKey: "nav.group.investments",
    items: [
      { labelKey: "nav.investments", to: "/investments", icon: CandlestickChart, hintKey: "help.investments" },
      { labelKey: "nav.crypto", to: "/crypto", icon: Coins, hintKey: "help.crypto" },
      { labelKey: "nav.roi", to: "/roi", icon: Calculator, hintKey: "help.roi" },
    ],
  },
  {
    labelKey: "nav.group.directories",
    items: [
      { labelKey: "nav.categories", to: "/categories", icon: Tags, hintKey: "help.categories" },
      // Единицы отдельным разделом: правят их раз в жизни, но лежали они
      // внизу справочников, и ради одного редкого действия приходилось
      // листать мимо всех людей и магазинов.
      { labelKey: "nav.units", to: "/units", icon: Ruler, hintKey: "help.units" },
      { labelKey: "nav.products", to: "/products", icon: ShoppingBasket, hintKey: "help.products" },
      { labelKey: "nav.directories", to: "/directories", icon: Users, hintKey: "help.directories" },
    ],
  },
];

/**
 * Пункты, прижатые к низу меню.
 *
 * Настройки — не раздел учёта, а место, куда ходят раз в месяц. В общем
 * списке они были последней строкой последней группы и уезжали за нижний
 * край вместе с ним; внизу они всегда на виду и всегда на одном месте, где
 * бы ни закончился список разделов.
 */
export const NAV_FOOTER: NavItem[] = [
  { labelKey: "nav.settings", to: "/settings", icon: Settings, hintKey: "help.settings" },
];

/**
 * Плоский список — для тех мест, которым нужен просто поиск по адресу
 * (заголовок страницы в шапке). Собирается из групп, чтобы не разъехаться с
 * меню при добавлении раздела.
 */
export const NAV_ITEMS: NavItem[] = [...NAV_GROUPS.flatMap((group) => group.items), ...NAV_FOOTER];
