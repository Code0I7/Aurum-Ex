import { useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { ChartTooltipBox } from "@/components/charts/ChartTooltipBox";
import { useTranslation } from "@/lib/i18n";
import { formatCurrency } from "@/lib/format";
import { useReservations } from "@/hooks/useGoals";
import { currentZoom, layoutViewport } from "@/lib/scale";
import { useNetWorthSummary } from "@/hooks/useNetWorth";
import type { AccountReservation, DashboardAccountBalance } from "@/types";

/**
 * Остатки по счетам — «сколько у меня сейчас и где».
 *
 * Всегда текущие, независимо от выбранного сверху периода: вопрос от периода
 * не зависит, и подменять ответ остатком на конец марта значило бы врать
 * ровно тому, кто открыл дашборд, чтобы понять, сколько у него денег.
 */
export function AccountBalancesCard({ accounts }: { accounts: DashboardAccountBalance[] }) {
  const { t } = useTranslation();
  const { data: reservations } = useReservations();
  // Быстрые деньги показываются здесь, а не только на вкладке капитала:
  // обзор открывают первым, и вопрос «сколько я могу потратить» задают
  // раньше, чем «сколько я стою». Период короткий — само число от него
  // не зависит, берётся текущее состояние.
  const { data: netWorth } = useNetWorthSummary("30d");

  if (accounts.length === 0) return null;

  const byAccount = new Map<number, AccountReservation[]>();
  for (const item of reservations ?? []) {
    const list = byAccount.get(item.account_id);
    if (list) list.push(item);
    else byAccount.set(item.account_id, [item]);
  }

  const total = accounts
    .filter((account) => account.nature === "asset")
    .reduce((sum, account) => sum + Number(account.balance), 0);

  return (
    <Card>
      <CardHeader className="items-start">
        <div>
          <CardTitle>{t("dashboard.accountsTitle")}</CardTitle>
          <p className="mt-1 text-xs text-text-muted">{t("dashboard.accountsHint")}</p>
        </div>
        <span className="shrink-0 text-right">
          <span className="block text-lg font-semibold tabular-nums">{formatCurrency(total)}</span>
          {netWorth && (
            <span className="block text-xs text-text-muted">
              {t("netWorth.liquid")}:{" "}
              <span className="tabular-nums">{formatCurrency(netWorth.liquid)}</span>
            </span>
          )}
        </span>
      </CardHeader>
      <CardContent>
        <ul className="divide-y divide-gridline">
          {accounts.map((account) => {
            const balance = Number(account.balance);
            const reserved = Number(account.reserved);
            return (
              <li key={account.account_id} className="py-2">
                <div className="flex items-center justify-between gap-3">
                <span className="min-w-0">
                  <span className="block truncate text-sm">{account.name}</span>
                  {/* Отложенное дописывается второй строкой только когда оно
                      есть: у большинства счетов резерва нет, и пустая строка
                      растянула бы список без пользы. */}
                  {reserved > 0 && (
                    <span className="block text-xs text-text-muted">
                      {t("dashboard.reservedAvailable", {
                        reserved: formatCurrency(reserved),
                        available: formatCurrency(account.available),
                      })}
                    </span>
                  )}
                </span>
                <span
                  className="shrink-0 text-sm font-medium tabular-nums"
                  style={{ color: balance < 0 ? "var(--danger)" : "var(--text-primary)" }}
                >
                  {formatCurrency(balance)}
                </span>
                </div>
                <AccountBar
                  balance={balance}
                  segments={byAccount.get(account.account_id) ?? []}
                  freeLabel={t("dashboard.freeSegment")}
                />
              </li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}

/**
 * Полоса остатка: свободное одним куском, отложенное — отдельными.
 *
 * Смысл в том, чтобы отложенное было видно как часть счёта, а не как
 * отдельная сумма где-то ещё. Деньги никуда не перекладывались: это тот же
 * остаток, часть которого обещана другой задаче.
 *
 * Отрезков нет — нет и полосы: у большинства счетов резерва не бывает, и
 * ровная зелёная черта под каждой строкой была бы украшением без смысла.
 *
 * Сверх остатка отрезки не рисуются: отложить больше, чем лежит на счёте,
 * нельзя, и доля считается от самого остатка.
 *
 * Соседние цели разделяются вырезом цветом карточки, а не оттенком:
 * оттенок по номеру означал бы, что отрезок меняет цвет от появления
 * соседней цели, — а вырез стоит там же, где граница, и от соседей не
 * зависит. Раньше вырез был в один пиксель на полосе в полтора, и три цели
 * подряд читались как одна золотая заливка.
 */
function AccountBar({
  balance,
  segments,
  freeLabel,
}: {
  balance: number;
  segments: AccountReservation[];
  freeLabel: string;
}) {
  const [hover, setHover] = useState<{ label: string; amount: number; x: number; y: number } | null>(null);

  if (segments.length === 0 || balance <= 0) return null;

  const reserved = segments.reduce((sum, item) => sum + Number(item.amount), 0);
  const free = Math.max(0, balance - reserved);

  function follow(label: string, amount: number) {
    return (event: React.PointerEvent) => setHover({ label, amount, x: event.clientX, y: event.clientY });
  }

  return (
    <>
      <span
        className="mt-1.5 flex h-2 overflow-hidden rounded-full bg-surface-2"
        role="presentation"
        onPointerLeave={() => setHover(null)}
        onPointerCancel={() => setHover(null)}
      >
        <span
          className="block h-full bg-success/70 transition-[width,filter] hover:brightness-125"
          style={{ width: `${(free / balance) * 100}%` }}
          onPointerEnter={follow(freeLabel, free)}
          onPointerMove={follow(freeLabel, free)}
          onPointerDown={follow(freeLabel, free)}
        />
        {segments.map((item, index) => (
          <span
            key={item.goal_id}
            // Золотом, а не цветом цели: цвет у целей не задаётся, а
            // придумывать его по номеру значило бы, что один и тот же
            // отрезок меняет цвет при добавлении соседней цели.
            className="block h-full border-l-2 border-surface-1 bg-accent transition-[width,filter] hover:brightness-125"
            style={{
              width: `${(Number(item.amount) / balance) * 100}%`,
              // Совсем маленькая цель иначе исчезает целиком под вырезом:
              // отрезок, которого не видно, хуже неточной ширины.
              minWidth: index === segments.length - 1 ? undefined : "5px",
            }}
            onPointerEnter={follow(item.goal_name, Number(item.amount))}
            onPointerMove={follow(item.goal_name, Number(item.amount))}
            onPointerDown={follow(item.goal_name, Number(item.amount))}
          />
        ))}
      </span>

      {/* Своя подсказка вместо браузерной. Нативный title появляется через
          секунду, системным шрифтом и всегда снизу справа — на полосе
          высотой в два пикселя это значит, что до подписи нужно ещё
          дождаться. Рамка та же, что у подсказок графиков: одно оформление
          на все всплывающие подписи. */}
      {hover ? <BarTooltip {...hover} /> : null}
    </>
  );
}

/** Подсказка у курсора. Рисуется порталом в body: полоса лежит в карточке
 *  со своим переполнением, и обычный absolute обрезался бы её краем. */
function BarTooltip({ label, amount, x, y }: { label: string; amount: number; x: number; y: number }) {
  const [box, setBox] = useState<{ width: number; height: number } | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  // Размер меряется после отрисовки: до неё неизвестно, сколько места
  // займёт название цели, а от него зависит, поместится ли подсказка
  // справа от курсора.
  useLayoutEffect(() => {
    const node = ref.current;
    if (node) setBox({ width: node.offsetWidth, height: node.offsetHeight });
  }, [label, amount]);

  // Координаты указателя приходят с экрана — уже увеличенные, — а станут
  // `left` и `top` элемента внутри увеличенного корня, где единицы другие.
  // Без деления подсказка отъезжала вниз и вправо ровно во столько раз, во
  // сколько увеличен интерфейс, и при 150% уже вылетала за край экрана: со
  // стороны выглядело так, будто подсказки на полосе просто нет.
  //
  // Размер самой подсказки делить не нужно: offsetWidth и offsetHeight, в
  // отличие от getBoundingClientRect, отдают разметочные.
  const zoom = currentZoom();
  const pointerX = x / zoom;
  const pointerY = y / zoom;
  const room = layoutViewport().width;

  const GAP = 12;
  const left =
    box && pointerX + GAP + box.width > room ? pointerX - GAP - box.width : pointerX + GAP;
  const top =
    box && pointerY - box.height - GAP < 0 ? pointerY + GAP : pointerY - (box?.height ?? 0) - GAP;

  return createPortal(
    <div
      ref={ref}
      style={{ left, top, opacity: box ? 1 : 0 }}
      className="pointer-events-none fixed z-[70]"
    >
      <ChartTooltipBox className="whitespace-nowrap text-xs">
        <p className="text-text-muted">{label}</p>
        <p className="font-medium tabular-nums text-text-primary">{formatCurrency(amount)}</p>
      </ChartTooltipBox>
    </div>,
    document.body
  );
}
