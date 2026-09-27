import { useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { ChartTooltipBox } from "@/components/charts/ChartTooltipBox";
import { AccountDetailsModal } from "@/components/dashboard/AccountDetailsModal";
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
export function AccountBalancesCard({
  accounts,
  className,
}: {
  accounts: DashboardAccountBalance[];
  /** Высота задаётся снаружи: в сетке обзора карточка тянется до низа
   *  своей строки, иначе рядом с соседкой у неё разный нижний край. */
  className?: string;
}) {
  const { t, currency: base } = useTranslation();
  const { data: reservations } = useReservations();
  // Быстрые деньги показываются здесь, а не только на вкладке капитала:
  // обзор открывают первым, и вопрос «сколько я могу потратить» задают
  // раньше, чем «сколько я стою». Период короткий — само число от него
  // не зависит, берётся текущее состояние.
  const { data: netWorth } = useNetWorthSummary("30d");
  // Какой счёт раскрыт подробностями. Null — окно закрыто; на полосу
  // отрезков на телефоне не нажать, а вопрос «на что отложено» задают именно
  // там.
  const [detailed, setDetailed] = useState<DashboardAccountBalance | null>(null);

  if (accounts.length === 0) return null;

  const byAccount = new Map<number, AccountReservation[]>();
  for (const item of reservations ?? []) {
    const list = byAccount.get(item.account_id);
    if (list) list.push(item);
    else byAccount.set(item.account_id, [item]);
  }

  // Итог считается по пересчитанным остаткам: складывать евро с рублями
  // как голые числа — ровно та ошибка, из-за которой сто евро выглядели
  // как сто рублей. Знак «примерно» ставится, когда валют больше одной:
  // пересчёт сделан по сегодняшнему курсу, а он завтра другой.
  // Итог — сумма всех строк списка, включая кредитки с минусом.
  //
  // Раньше складывались одни счета-активы, и итог молча расходился со
  // списком прямо под ним: 127 тысяч сверху, а в списке кредитка на −54.
  // Выглядело так, будто минус сидит внутри этих 127, — а его там не было
  // вовсе. Число над списком обязано быть суммой этого списка.
  const total = accounts.reduce((sum, account) => sum + Number(account.balance_base), 0);
  const mixed = new Set(accounts.map((account) => account.currency)).size > 1;

  return (
    <Card className={className}>
      <CardHeader className="items-start">
        <div>
          <CardTitle>{t("dashboard.accountsTitle")}</CardTitle>
          <p className="mt-1 text-xs text-text-muted">{t("dashboard.accountsHint")}</p>
        </div>
        <span className="shrink-0 text-right">
          <span className="block text-lg font-semibold tabular-nums">
            {mixed && "≈ "}
            {formatCurrency(total)}
          </span>
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
                {/* Вся строка — кнопка: на телефоне цель для пальца должна
                    быть шириной в строку, а не в отрезок полосы. */}
                <button
                  type="button"
                  onClick={() => setDetailed(account)}
                  title={t("dashboard.accountDetails")}
                  className="flex w-full items-center justify-between gap-3 text-left"
                >
                <span className="min-w-0">
                  <span className="block truncate text-sm">{account.name}</span>
                  {/* Отложенное дописывается второй строкой только когда оно
                      есть: у большинства счетов резерва нет, и пустая строка
                      растянула бы список без пользы. */}
                  {reserved > 0 && (
                    <span className="block text-xs text-text-muted">
                      {t("dashboard.reservedAvailable", {
                        reserved: formatCurrency(reserved, account.currency),
                        available: formatCurrency(account.available, account.currency),
                      })}
                    </span>
                  )}
                </span>
                <span
                  className="shrink-0 text-sm font-medium tabular-nums"
                  style={{ color: balance < 0 ? "var(--danger)" : "var(--text-primary)" }}
                >
                  {formatCurrency(balance, account.currency)}
                  {/* Вторая строка — сколько это в валюте установки, по
                      сегодняшнему курсу. Только у валютного счёта: у своего
                      это было бы одно и то же число дважды. */}
                  {account.currency !== base && (
                    <span className="block text-xs font-normal text-text-muted">
                      ≈ {formatCurrency(account.balance_base, base)}
                    </span>
                  )}
                </span>
                </button>
                <AccountBar
                  balance={balance}
                  segments={byAccount.get(account.account_id) ?? []}
                  freeLabel={t("dashboard.freeSegment")}
                  currency={account.currency}
                />
              </li>
            );
          })}
        </ul>
      </CardContent>
      {/* Окно живёт здесь, а не в строке: счетов бывает десяток, и десять
          закрытых окон в разметке ни к чему. */}
      <AccountDetailsModal
        account={detailed}
        reservations={detailed ? byAccount.get(detailed.account_id) ?? [] : []}
        onClose={() => setDetailed(null)}
      />
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
  // Валюта счёта. Отложенное лежит на нём же, в его валюте: подписать его
  // значком валюты установки значило бы сказать, что на евровой карте
  // отложены рубли.
  currency,
}: {
  balance: number;
  segments: AccountReservation[];
  freeLabel: string;
  currency: string;
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
      {/* Отрезки — отдельными скруглёнными полосками с просветом, а не
          вырезом внутри одной полосы.

          Вырез рисовался рамкой цвета карточки, и заметен был ровно тогда,
          когда этот цвет отличался от цвета полосы. У части оформлений не
          отличался: три цели подряд сливались в одну жёлтую заливку, и
          границы находились только наведением. Просвет — это настоящая
          пустота, сквозь неё виден фон, какой бы он ни был, и граница
          видна в любой теме. */}
      <span
        className="mt-1.5 flex h-2 gap-[3px]"
        role="presentation"
        onPointerLeave={() => setHover(null)}
        onPointerCancel={() => setHover(null)}
      >
        <span
          className="block h-full rounded-full bg-success/70 transition-[width,filter] hover:brightness-125"
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
            className="block h-full rounded-full bg-accent transition-[width,filter] hover:brightness-125"
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
      {hover ? <BarTooltip {...hover} currency={currency} /> : null}
    </>
  );
}

/** Подсказка у курсора. Рисуется порталом в body: полоса лежит в карточке
 *  со своим переполнением, и обычный absolute обрезался бы её краем. */
function BarTooltip({
  label,
  amount,
  x,
  y,
  currency,
}: {
  label: string;
  amount: number;
  x: number;
  y: number;
  currency: string;
}) {
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
        <p className="font-medium tabular-nums text-text-primary">
          {formatCurrency(amount, currency)}
        </p>
      </ChartTooltipBox>
    </div>,
    document.body
  );
}
