import { markSetupRequired, markSignedOut } from "@/lib/auth";

const API_BASE = "/api";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    // Сессия живёт в HttpOnly-куке: заголовок Authorization больше не
    // собирается вручную, браузер прикладывает куку сам — но только если
    // явно разрешить отправку учётных данных.
    credentials: "same-origin",
    ...init,
  });

  if (response.status === 401) {
    // Сессия кончилась или была оборвана (выход на другом устройстве,
    // смена пароля) — сообщаем LoginGate, чтобы он показал вход сразу, а
    // не после того, как все запросы на странице по очереди отвалятся.
    markSignedOut();
  }

  if (response.status === 428) {
    // Пароль ещё не задан: установка новая. Показывать надо первичную
    // настройку, а не форму входа, иначе войти будет некуда.
    markSetupRequired();
  }

  if (!response.ok) {
    const body = await response.text();
    let message = body || response.statusText;
    try {
      const parsed = JSON.parse(body) as { detail?: unknown };
      if (typeof parsed.detail === "string") message = parsed.detail;
    } catch {
      // body wasn't JSON — fall back to the raw text set above
    }
    throw new ApiError(response.status, message);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};
