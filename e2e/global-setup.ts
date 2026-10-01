import { mkdir } from "node:fs/promises";
import path from "node:path";
import { request, type FullConfig } from "@playwright/test";

export const STATE_PATH = path.join(import.meta.dirname, ".auth", "state.json");

/**
 * Вход один раз на весь прогон.
 *
 * Эти спеки написаны до того, как у приложения появился собственный вход, и
 * из-за него перестали работать целиком: и браузер упирался в страницу
 * входа, и фикстура `request` получала 401 на первом же обращении к API.
 *
 * Логин делается здесь, а не в каждом тесте: сессия у приложения
 * серверная, и шестьдесят входов подряд проверяли бы вход, а не то, ради
 * чего тест написан. Куку сессии Playwright сохраняет в файл состояния, и
 * его подхватывают и браузер, и `request` (см. playwright.config.ts).
 *
 * Учётная запись заводится самим приложением из AURUM_ADMIN_PASSWORD при
 * старте контейнера — см. run.sh. Поэтому здесь именно вход, а не
 * первичная настройка: настройка отвечает 409, если учётная запись уже
 * есть, и прогон зависел бы от того, успел ли backend её создать.
 */
export default async function globalSetup(config: FullConfig) {
  const baseURL =
    config.projects[0]?.use?.baseURL ?? process.env.AURUM_E2E_BASE_URL ?? "http://localhost:3100";
  const username = process.env.AURUM_E2E_USERNAME ?? "admin";
  const password = process.env.AURUM_E2E_PASSWORD;
  if (!password) {
    throw new Error("AURUM_E2E_PASSWORD не задан — запускайте через e2e/run.sh");
  }

  const context = await request.newContext({ baseURL });
  const resp = await context.post("/api/auth/login", { data: { username, password } });
  if (!resp.ok()) {
    throw new Error(
      `вход не удался: ${resp.status()} ${await resp.text()}\n` +
        "Проверьте, что стенд поднят с AURUM_ADMIN_PASSWORD — его ставит run.sh."
    );
  }

  await mkdir(path.dirname(STATE_PATH), { recursive: true });
  await context.storageState({ path: STATE_PATH });
  await context.dispose();
}
