import { MonthSelector } from "@/components/layout/MonthSelector";
import { YearSelector } from "@/components/layout/YearSelector";
import { StatCard } from "@/components/dashboard/StatCard";
import { CategoryBreakdownCard } from "@/components/dashboard/CategoryBreakdownCard";
import { RecentTransactionsCard } from "@/components/dashboard/RecentTransactionsCard";
import { AccountBalancesCard } from "@/components/dashboard/AccountBalancesCard";
import { LargestExpensesCard } from "@/components/dashboard/LargestExpensesCard";
import { RatesCard } from "@/components/dashboard/RatesCard";
import { MonthlyFlowCard } from "@/components/dashboard/MonthlyFlowCard";
import { AlertBanner } from "@/components/insights/AlertBanner";
import { useDashboardSummary } from "@/hooks/useDashboard";
import { useTransactionYears } from "@/hooks/useTransactions";
import { formatCurrency, formatSignedCurrency, formatTransactionDate } from "@/lib/format";
import { useViewDefault } from "@/hooks/useViewDefault";
import { useSessionState } from "@/hooks/useSessionState";
import { useAppSettings } from "@/hooks/useSettings";
import { useTranslation } from "@/lib/i18n";
import type { DashboardRange } from "@/types";

/** Share of income left over after spending (net / real_income). `null` when
 * there was no income to take a share of, rather than a misleading 0%. */
function savingsRate(realIncome: number, net: number): number | null {
  return realIncome > 0 ? (net / realIncome) * 100 : null;
}

function formatPercent(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(0)}%`;
}

export function DashboardPage() {
  const { t } = useTranslation();
  const now = new Date();
  const [year, setYear] = useSessionState("aurum:dashboard-year", now.getFullYear());
  const [month, setMonth] = useSessionState("aurum:dashboard-month", now.getMonth() + 1);
  // Период по умолчанию настраивается; год — если ничего не выбрано.
  // Месяц при многолетней истории случайный срез, а «за всё время»
  // отвечает на вопрос «как было вообще», тогда как открывают приложение
  // обычно с вопросом «как у меня сейчас».
  const { data: settings } = useAppSettings();
  const [range, setRange] = useViewDefault<DashboardRange>(
    "aurum:dashboard-range",
    settings?.default_dashboard_range,
    "year",
  );
  const { data: years } = useTransactionYears();

  const { data, isLoading, isError } = useDashboardSummary(year, month, range);
  const rate = data ? savingsRate(Number(data.real_income), Number(data.net)) : null;

  const ranges: Array<{ key: DashboardRange; label: string }> = [
    { key: "month", label: t("dashboard.rangeMonth") },
    { key: "year", label: t("dashboard.rangeYear") },
    { key: "all", label: t("dashboard.rangeAll") },
  ];

  return (
    <div className="space-y-5">
      <AlertBanner excludeKeys={["risky_allocation_exceeded"]} />

      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-1">
          {ranges.map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => setRange(item.key)}
              className={`rounded-md px-3 py-1.5 text-xs font-medium ${
                range === item.key
                  ? "bg-surface-2 text-text-primary"
                  : "text-text-muted hover:bg-surface-2 hover:text-text-primary"
              }`}
            >
              {item.label}
            </button>
          ))}
          {/* Границы периода подписаны датами: при «за всё время» интерфейс
              сам не знает, с какого дня идёт история. */}
          {data?.start_date && data.end_date && (
            <span className="ml-auto text-xs text-text-muted">
              {formatTransactionDate(data.start_date, true)} — {formatTransactionDate(data.end_date, true)}
            </span>
          )}
        </div>

        {/* Выбор месяца и года прячется, когда он ни на что не влияет:
            переключатель, который ничего не меняет, — обещание, которого
            приложение не выполняет. */}
        {range !== "all" && (
          // Выравнивание вправо, под даты периода строкой выше. При выборе
          // месяца год и так стоит справа — месяц перед ним занимает всё
          // свободное место; а когда выбран год, он оставался один и
          // прилипал к левому краю, хотя место его не менялось.
          <div className="flex items-center justify-end gap-3">
            {range === "month" && (
              <div className="min-w-0 flex-1">
                <MonthSelector month={month} onChange={setMonth} />
              </div>
            )}
            <YearSelector years={years ?? [now.getFullYear()]} year={year} onChange={setYear} />
          </div>
        )}
      </div>

      {isError && (
        <p className="rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
          {t("dashboard.errorLoading")}
        </p>
      )}

      {/* Пять карточек, когда введены часы, иначе четыре. Заработок за
          час не заменяет норму сбережений: это разные вопросы — «сколько
          я оставляю себе» и «во что мне обходится покупка», — и подменять
          один другим значит убирать метрику, на которую человек только
          что смотрел. */}
      {/* Последняя карточка, оставшаяся одна в строке, растягивается на всю
          ширину. На телефоне колонок две, а карточек пять — пятая иначе
          висит половинкой рядом с пустотой. Правило через nth-child, а не
          через счёт карточек в коде: их число зависит от данных, и держать
          два места в согласии пришлось бы вручную. */}
      {/* Сколько карточек в ряд — решает место, а не точка перелома.
          Ступенями это не выражается: пятая колонка появлялась уже на 1024,
          и на карточку оставалось меньше двухсот точек — суммы в семь
          знаков не помещались. А ступеней нужно было бы столько же, сколько
          бывает ширин.

          Поэтому колонка объявлена «не уже трёхсот точек, дальше поровну»,
          и браузер сам укладывает столько, сколько влезло: пять на широком
          мониторе, три при 200%, две при 300%. На телефоне ступень всё же
          нужна — там триста точек это вся ширина, и по этому правилу
          вышла бы одна карточка в ряд вместо двух.

          Последняя карточка, оставшаяся одна в строке, растягивается на всю
          ширину: на телефоне колонок две, а карточек пять, и пятая иначе
          висит половинкой рядом с пустотой. Правило через nth-child, а не
          через счёт карточек в коде: их число зависит от данных, и держать
          два места в согласии пришлось бы вручную. Выше телефона правило
          снимается — сколько там колонок, разметка уже не знает. */}
      <div className="grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-[repeat(auto-fit,minmax(300px,1fr))] [&>*:last-child:nth-child(odd)]:col-span-2 md:[&>*:last-child:nth-child(odd)]:col-span-1">
        <StatCard
          label={t("dashboard.statRealIncomeLabel")}
          value={isLoading ? "…" : formatCurrency(data?.real_income ?? 0)}
          hintKey="help.realIncome"
          tone="success"
        />
        <StatCard
          label={t("dashboard.statSpentLabel")}
          value={isLoading ? "…" : formatCurrency(data?.spent ?? 0)}
          hintKey="help.spent"
          tone="danger"
        />
        <StatCard
          label={t("dashboard.statNetLabel")}
          value={isLoading ? "…" : formatSignedCurrency(data?.net ?? 0)}
          hintKey="help.net"
          tone={Number(data?.net ?? 0) >= 0 ? "success" : "danger"}
        />
        <StatCard
          label={t("dashboard.statSavingsRateLabel")}
          value={isLoading ? "…" : rate === null ? "—" : formatPercent(rate)}
          hintKey="help.savingsRate"
          tone={rate === null ? "default" : rate >= 0 ? "success" : "danger"}
        />
        {/* Заработок за час показывается всегда, и прочерком тоже — как
            норма сбережений рядом. Раньше карточка при пустых часах
            исчезала, и ряд показателей менял состав от периода к периоду:
            человек искал глазами то, что было тут в прошлом месяце. Прочерк
            честнее пропажи: он говорит «данных нет», а не «показателя не
            существует». */}
        <StatCard
          label={t("dashboard.statHourlyLabel")}
          value={
            isLoading ? "…" : data?.earned_per_hour ? formatCurrency(data.earned_per_hour) : "—"
          }
          hintKey="help.hourly"
          // Подпись здесь остаётся: число часов меняется вместе с суммой и
          // объясняет именно её, а не понятие.
          caption={
            data?.earned_per_hour
              ? t("dashboard.statHourlyCaption", { hours: Number(data.hours_worked) })
              : t("dashboard.statHourlyEmpty")
          }
          tone="default"
        />
      </div>

      <MonthlyFlowCard points={data?.monthly ?? []} daily={data?.daily ?? []} />

      {/* Пять карточек в две колонки, каждая на своём месте в сетке.

          Раньше «Последние транзакции» лежали во всю ширину под всем, и
          справа от них оставалась пустая полоса в треть экрана. Теперь они
          стоят под разбивкой по категориям, в той же колонке, а справа от
          них — крупные траты.

          Разбивка по категориям занимает две строки: ровно столько, сколько
          вместе занимают счета и курсы. Так нижний край у левой и правой
          колонки совпадает, а не расходится на случайную величину.

          minmax(0, …) у обеих колонок — не украшение. Без него доля
          отсчитывается от содержимого, а не от места: таблица операций не
          умеет быть уже своих столбцов, и колонка раздувалась под неё —
          вся страница выезжала за экран, и внизу появлялась горизонтальная
          прокрутка. С нулевым минимумом колонка обязана уместиться, а
          тесное содержимое разбирается со своей теснотой само.

          Порядок на телефоне свой: категории, счета, курсы, транзакции,
          крупные траты. В один столбец раскладка читается не так, как в
          два, и связывать их одним порядком значило бы испортить одну ради
          другой. На узком экране сетка выключена, и порядок задают числа;
          на широком числа ни на что не влияют, и место каждой карточки
          названо строкой и колонкой. */}
      <div className="flex flex-col gap-4 lg:grid lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        {/* Доходы и расходы по категориям — рядом, доходы слева, как в
            ряду показателей над ними. Каждая карточка в половину прежней
            ширины, поэтому круг у них над списком, а не сбоку. На телефоне
            они встают друг под другом. */}
        <div className="order-1 grid gap-4 sm:grid-cols-2 lg:col-start-1 lg:row-start-1 lg:row-span-2">
          <CategoryBreakdownCard
            title={t("dashboard.incomeByCategoryTitle")}
            emptyLabel={t("dashboard.noIncomeThisPeriod")}
            items={data?.income_by_category ?? []}
            viewKey="income"
            className="h-full"
          />
          <CategoryBreakdownCard
            title={t("dashboard.spendingByCategoryTitle")}
            emptyLabel={t("dashboard.noExpensesThisMonth")}
            items={data?.spending_by_category ?? []}
            viewKey="spending"
            className="h-full"
          />
        </div>

        {/* h-full у каждой: сетка растягивает ячейку, но карточка внутри
            остаётся своей высоты, и нижние края в строке расходятся. */}
        <div className="order-2 lg:col-start-2 lg:row-start-1">
          <AccountBalancesCard accounts={data?.accounts ?? []} className="lg:h-full" />
        </div>

        <div className="order-3 lg:col-start-2 lg:row-start-2">
          <RatesCard className="lg:h-full" />
        </div>

        <div className="order-4 lg:col-start-1 lg:row-start-3">
          <RecentTransactionsCard year={year} month={month} className="lg:h-full" />
        </div>

        <div className="order-5 lg:col-start-2 lg:row-start-3">
          <LargestExpensesCard items={data?.largest_expenses ?? []} className="lg:h-full" />
        </div>
      </div>
    </div>
  );
}
