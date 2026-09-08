/**
 * Расчёт доходности вложения с довложениями.
 *
 * Считается **по месяцам**, а не по годам: деньги, отложенные в марте, к
 * декабрю успевают поработать девять месяцев, и годовой шаг эту разницу
 * теряет. Довложение вносится **в конце месяца** — то есть проценты на него
 * начинают начисляться со следующего, как и бывает, когда откладываешь с
 * зарплаты.
 *
 * Доходность разделена на две части, и это главное отличие от расчёта «в
 * один процент»:
 *
 *   * **выплаты** — дивиденды, купоны, арендная плата. Это живые деньги,
 *     которые приходят на счёт, и только на них можно жить;
 *   * **рост стоимости** — подорожание самого актива. Деньгами он
 *     становится лишь при продаже.
 *
 * Сложить их в одну цифру можно, но тогда исчезает ответ на вопрос
 * «сколько мне будет капать», а именно его обычно и задают.
 *
 * Ещё одно намеренное разделение — в итогах: сколько внесено руками и
 * сколько заработали проценты. Без него график роста выглядит убедительнее,
 * чем есть на самом деле: большая часть суммы там нередко просто донесена
 * из зарплаты.
 */

export interface RoiInput {
  /** Стартовая сумма вложения. */
  initial: number;
  /**
   * Месячная доходность выплатами долей единицы: 0.01 — один процент в
   * месяц.
   *
   * Именно месячная, а не годовая, и это важно. Когда человек говорит
   * «квартира приносит 5 000 в месяц», он имеет в виду ровно 5 000 в первый
   * же месяц. Если свести эту сумму к годовой ставке и вернуть обратно через
   * корень двенадцатой степени, получится 4 744 — формально корректно, но
   * человек ввёл одно число, а увидел другое, и доверие к калькулятору на
   * этом заканчивается. Поэтому месячная ставка здесь первична, а годовая
   * считается из неё для справки.
   */
  payoutMonthlyRate: number;
  /** Годовой рост стоимости самого актива, в процентах. */
  growthRatePercent: number;
  /** Сколько докладывать каждый месяц. Ноль — не докладывать. */
  monthlyContribution: number;
  /** Ежегодная индексация довложений, в процентах: зарплата растёт, и
   * откладывать со временем получается больше. */
  contributionIndexPercent: number;
  /** Реинвестировать ли выплаты. Выключено — выплаты копятся отдельно и в
   * работу не идут: так считают те, кто живёт с дивидендов. */
  reinvestPayouts: boolean;
  /** Горизонт расчёта в годах. */
  years: number;
}

export interface RoiYear {
  year: number;
  /** Стоимость актива на конец года. */
  capital: number;
  /** Выплаты, полученные за год. */
  payouts: number;
  /** Выплаты, полученные за всё время. */
  payoutsTotal: number;
  /** Внесено руками за всё время, включая стартовую сумму. */
  contributed: number;
  /** Всего денег: капитал плюс невложенные выплаты. */
  total: number;
}

export interface RoiResult {
  years: RoiYear[];
  /** Внесено руками за весь срок. */
  contributed: number;
  /** Заработано процентами: итог минус внесённое. */
  earned: number;
  /** Итог на конец срока. */
  total: number;
  /** Выплаты в первый месяц — «сколько будет капать» сразу. */
  firstMonthPayout: number;
  /** Годовая доходность выплатами, в процентах — производная от месячной. */
  payoutAnnualPercent: number;
  /** Через сколько лет выплаты вернут стартовое вложение. Null, если
   * выплат нет вовсе. */
  paybackYears: number | null;
}

/** Годовая ставка в месячную. Через корень двенадцатой степени, а не
 * делением на 12: при делении месячная ставка, начисленная двенадцать раз,
 * даёт за год больше заявленного, и расчёт незаметно завышает результат. */
export function monthlyRate(annualPercent: number): number {
  return Math.pow(1 + annualPercent / 100, 1 / 12) - 1;
}

/** Месячная ставка в годовую — для подписи под полем ввода. */
export function annualFromMonthly(monthlyPercent: number): number {
  return (Math.pow(1 + monthlyPercent / 100, 12) - 1) * 100;
}

export function calculateRoi(input: RoiInput): RoiResult {
  const { initial, monthlyContribution, reinvestPayouts, years } = input;
  const payoutMonthly = input.payoutMonthlyRate;
  const growthMonthly = monthlyRate(input.growthRatePercent);

  let capital = initial;
  let contributed = initial;
  let payoutsTotal = 0;
  let payoutsAside = 0;
  let contribution = monthlyContribution;
  let firstMonthPayout = 0;

  const rows: RoiYear[] = [];
  let payoutsThisYear = 0;

  for (let month = 1; month <= years * 12; month += 1) {
    // Выплаты и рост считаются от капитала на начало месяца — довложение
    // этого месяца в них ещё не участвует, оно придёт в конце.
    const payout = capital * payoutMonthly;
    if (month === 1) firstMonthPayout = payout;

    capital *= 1 + growthMonthly;
    payoutsTotal += payout;
    payoutsThisYear += payout;

    if (reinvestPayouts) capital += payout;
    else payoutsAside += payout;

    // Довложение в конце месяца: работать оно начнёт со следующего.
    if (contribution > 0) {
      capital += contribution;
      contributed += contribution;
    }

    if (month % 12 === 0) {
      rows.push({
        year: month / 12,
        capital,
        payouts: payoutsThisYear,
        payoutsTotal,
        contributed,
        total: capital + payoutsAside,
      });
      payoutsThisYear = 0;
      // Индексация довложений раз в год: зарплата растёт, и откладывать
      // получается больше.
      contribution *= 1 + input.contributionIndexPercent / 100;
    }
  }

  const total = capital + payoutsAside;
  // Окупаемость считается по выплатам без реинвестирования: вопрос «когда
  // вернутся вложенные деньги» про живые поступления, а не про то, во что
  // они успеют вырасти.
  const annualPayout = initial * payoutMonthly * 12;

  return {
    years: rows,
    contributed,
    earned: total - contributed,
    total,
    firstMonthPayout,
    payoutAnnualPercent: annualFromMonthly(payoutMonthly * 100),
    paybackYears: annualPayout > 0 ? initial / annualPayout : null,
  };
}
