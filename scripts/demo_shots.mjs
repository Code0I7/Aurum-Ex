/**
 * Снимки экранов для README — по демонстрационным данным.
 *
 * Запускается против одноразовой установки, поднятой отдельным compose-проектом
 * и засеянной scripts/demo_seed.py. Ничьих чужих данных не касается: адрес
 * передаётся снаружи, и это адрес демонстрационного стенда.
 *
 *   docker run --rm --network aurum-demo_default \
 *     -e BASE_URL=http://web -e LANG_CODE=ru -e OUT_DIR=/shots \
 *     -e DEMO_USER=demo -e DEMO_PASSWORD=... \
 *     -v /root/shots:/shots -v /root/aurum-ex/scripts:/scripts -w /scripts \
 *     mcr.microsoft.com/playwright:v1.62.1-noble \
 *     bash -c "npm i playwright@1.62.1 --silent && node demo_shots.mjs"
 *
 * Язык интерфейса хранится в браузере, поэтому ставится в localStorage до
 * первой отрисовки; валюта живёт на сервере и задаётся засевом.
 */
import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";

const base = process.env.BASE_URL ?? "http://web";
const language = process.env.LANG_CODE ?? "ru";
const outDir = `${process.env.OUT_DIR ?? "./shots"}/${language}`;
const username = process.env.DEMO_USER ?? "demo";
const password = process.env.DEMO_PASSWORD ?? "";

/** Что показываем и в каком порядке: раздел, адрес, оформление и тема.
 *
 *  Тринадцать разделов в золотом оформлении и светлой теме, а обзор снят
 *  ещё дважды — в современном тёмном и в классическом. Одним взглядом
 *  видно, что оформлений три и тёмная тема есть у каждого; тринадцать
 *  снимков каждого раздела в трёх видах никто смотреть не станет. */
const PAGES = [
  ["1-dashboard", "/", "gold", "light"],
  ["2-transactions", "/transactions", "gold", "light"],
  ["3-accounts", "/accounts", "gold", "light"],
  ["4-net-worth", "/net-worth", "gold", "light"],
  ["5-reports", "/reports", "gold", "light"],
  ["6-cash-flow", "/cash-flow", "gold", "light"],
  ["7-advice", "/advice", "gold", "light"],
  ["8-goals", "/goals", "gold", "light"],
  ["9-planning", "/planning", "gold", "light"],
  ["10-budget", "/budget", "gold", "light"],
  ["11-debts", "/debts", "gold", "light"],
  ["12-investments", "/investments", "gold", "light"],
  ["13-products", "/products", "gold", "light"],
  ["14-dashboard-modern-dark", "/", "modern", "dark"],
  ["15-dashboard-legacy", "/", "legacy", "light"],
];

await mkdir(outDir, { recursive: true });

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1440, height: 960 },
  // Обычная плотность, а не двойная. Тринадцать снимков в двух языках при
  // удвоении весят под десять мегабайт — столько картинок в репозитории
  // скачивает каждый, кто его клонирует. В сетке README снимок и так
  // показывается втрое меньше своего размера, и 1440 точек хватает с
  // запасом даже на экране с высокой плотностью.
  deviceScaleFactor: 1,
  locale: language === "ru" ? "ru-RU" : "en-US",
  timezoneId: "Europe/Moscow",
});

// Вход по API: страница логина в снимки не нужна, а руками пароль в форму
// никто не вводит — установка одноразовая и поднимается с заданным паролем.
const login = await context.request.post(`${base}/api/auth/login`, {
  data: { username, password },
});
if (!login.ok()) {
  throw new Error(`вход не удался: ${login.status()} ${await login.text()}`);
}

// Куку приходится переложить руками. Установка отдаёт её с признаком
// Secure — так и нужно за TLS, — а демонстрационный стенд стоит внутри
// сети docker по обычному http, и браузер такую куку молча выбрасывает.
// Снимок тогда выходит один и тот же на всех страницах: экран входа.
const [pair] = (login.headers()["set-cookie"] ?? "").split(";");
const [name, value] = pair.split("=");
if (!name || !value) throw new Error("сервер не выдал куку сессии");
await context.addCookies([{ name: name.trim(), value: value.trim(), url: base }]);

await context.addInitScript((value) => {
  window.localStorage.setItem("aurum:language", value);
}, language);

const page = await context.newPage();
for (const [name, path, design, theme] of PAGES) {
  await page.goto(`${base}${path}`, { waitUntil: "networkidle" });
  // Оформление и тема живут в браузере и применяются при загрузке, поэтому
  // ставятся после первого захода и страница перечитывается. Ставятся
  // каждый раз, а не только при смене: localStorage у страниц общий, и
  // тёмный обзор иначе утащил бы за собой все следующие снимки.
  await page.evaluate(
    ([chosenDesign, chosenTheme]) => {
      window.localStorage.setItem("aurum:design", chosenDesign);
      window.localStorage.setItem("aurum:theme", chosenTheme);
    },
    [design, theme]
  );
  await page.reload({ waitUntil: "networkidle" });
  // Графики рисуются после данных: без паузы в кадр попадает пустая рамка.
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${outDir}/${name}.png` });
  console.log(`${language}: ${name}`);
}

await browser.close();
