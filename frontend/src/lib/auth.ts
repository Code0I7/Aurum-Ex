import { useSyncExternalStore } from "react";

/**
 * Состояние входа на клиенте.
 *
 * Пришло на смену хранению Basic Auth-заголовка в sessionStorage: теперь
 * сессия живёт в HttpOnly-куке, которую браузер прикладывает сам, а скрипт
 * на странице прочитать не может. Поэтому здесь нет ни пароля, ни токена —
 * только ответ сервера на вопрос «кто я сейчас».
 *
 * Три состояния, и различать нужно все три:
 *  - setupComplete = false — пароль ещё не задан, показываем первичную
 *    настройку. Прятать её за формой входа нельзя: войти будет некуда;
 *  - authenticated = false — пароль есть, показываем вход;
 *  - authenticated = true — пускаем в приложение.
 */

export interface AuthState {
  setupComplete: boolean;
  authenticated: boolean;
  username: string | null;
  recoveryAvailable: boolean;
}

interface AuthStateResponse {
  setup_complete: boolean;
  authenticated: boolean;
  username: string | null;
  recovery_available: boolean;
}

const UNKNOWN: AuthState = {
  setupComplete: true,
  authenticated: false,
  username: null,
  recoveryAvailable: false,
};

let current: AuthState | null = null;
const listeners = new Set<() => void>();

function notify(): void {
  listeners.forEach((listener) => listener());
}

function adopt(payload: AuthStateResponse): AuthState {
  current = {
    setupComplete: payload.setup_complete,
    authenticated: payload.authenticated,
    username: payload.username,
    recoveryAvailable: payload.recovery_available,
  };
  notify();
  return current;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    // Кука сессии обязана уехать вместе с запросом и вернуться обратно.
    credentials: "same-origin",
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const raw = await response.text();
    let message = raw || response.statusText;
    try {
      const parsed = JSON.parse(raw) as { detail?: unknown };
      if (typeof parsed.detail === "string") message = parsed.detail;
    } catch {
      // тело не JSON — оставляем как есть
    }
    throw new Error(message);
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}

/** Спрашивает сервер, кто мы сейчас. Вызывается при загрузке страницы и
 * после каждого 401 (см. api/client.ts). */
export async function fetchAuthState(): Promise<AuthState> {
  try {
    const response = await fetch("/api/auth/state", { credentials: "same-origin" });
    if (!response.ok) return current ?? UNKNOWN;
    return adopt((await response.json()) as AuthStateResponse);
  } catch {
    // Бэкенд недоступен — это не повод показывать форму входа: страницы
    // приложения сами объяснят, что данные не загрузились.
    return current ?? UNKNOWN;
  }
}

export async function login(username: string, password: string): Promise<AuthState> {
  return adopt(await post<AuthStateResponse>("/auth/login", { username, password }));
}

/** Первичная настройка: пароль, а заодно язык и валюта установки. Язык и
 *  валюта необязательны — без них сервер оставляет свои значения. */
export async function completeSetup(
  username: string,
  password: string,
  language?: string,
  currency?: string
): Promise<AuthState> {
  return adopt(await post<AuthStateResponse>("/auth/setup", { username, password, language, currency }));
}

export async function logout(): Promise<void> {
  await post<void>("/auth/logout", {});
  await fetchAuthState();
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  await post<void>("/auth/password", {
    current_password: currentPassword,
    new_password: newPassword,
  });
  // Смена пароля обрывает все сессии, включая текущую, — состояние надо
  // перечитать, чтобы приложение сразу показало форму входа.
  await fetchAuthState();
}

export async function recoverPassword(recoveryKey: string, newPassword: string): Promise<void> {
  await post<void>("/auth/recover", { recovery_key: recoveryKey, new_password: newPassword });
  await fetchAuthState();
}

/** Помечает сессию просроченной, не дожидаясь ответа сервера. Дёргается из
 * обработчика 401, чтобы экран входа появился сразу. */
export function markSignedOut(): void {
  if (current && !current.authenticated) return;
  current = { ...(current ?? UNKNOWN), authenticated: false, username: null };
  notify();
}

/** Помечает, что установка ещё не настроена (ответ 428 от закрытого
 * эндпоинта). */
export function markSetupRequired(): void {
  if (current && !current.setupComplete) return;
  current = { ...(current ?? UNKNOWN), setupComplete: false, authenticated: false };
  notify();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useAuthState(): AuthState | null {
  return useSyncExternalStore(
    subscribe,
    () => current,
    () => current
  );
}
