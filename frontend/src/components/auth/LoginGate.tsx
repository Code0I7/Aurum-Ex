import { type ReactNode, useEffect } from "react";
import { Logo } from "@/components/layout/Logo";
import { LoginScreen } from "@/components/auth/LoginScreen";
import { fetchAuthState, useAuthState } from "@/lib/auth";

/**
 * Оборачивает всё приложение и решает, что показать: первичную настройку,
 * форму входа или само приложение.
 *
 * В отличие от прежней версии под Basic Auth, экран входа больше не
 * опциональный: защита теперь своя, и установки без пароля не бывает.
 * Пока состояние не получено, показывается заставка — иначе у вошедшего
 * пользователя на секунду мелькала бы форма входа.
 *
 * Сессия протухла или её оборвали на другом устройстве — обработчик 401 в
 * api/client.ts помечает состояние, useAuthState подхватывает это
 * реактивно, и вход появляется здесь сам собой.
 */
export function LoginGate({ children }: { children: ReactNode }) {
  const auth = useAuthState();

  useEffect(() => {
    void fetchAuthState();
  }, []);

  if (auth === null) {
    return (
      <div className="flex min-h-[var(--app-vh)] items-center justify-center bg-surface-0">
        <Logo variant="icon" size={44} className="animate-pulse" />
      </div>
    );
  }

  if (!auth.setupComplete) {
    return <LoginScreen mode="setup" recoveryAvailable={false} />;
  }

  if (!auth.authenticated) {
    return <LoginScreen mode="login" recoveryAvailable={auth.recoveryAvailable} />;
  }

  return <>{children}</>;
}
