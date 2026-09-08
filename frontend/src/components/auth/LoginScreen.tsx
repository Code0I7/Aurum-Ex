import { type FormEvent, useState } from "react";
import { Logo } from "@/components/layout/Logo";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { Input, Label } from "@/components/ui/Input";
import { completeSetup, login, recoverPassword } from "@/lib/auth";
import { useTranslation } from "@/lib/i18n";

type Mode = "login" | "setup" | "recover";

/**
 * Один экран на три состояния — вёрстка у них общая, отличается только
 * набор полей:
 *
 *  - setup — пароля ещё нет, установка новая. Показывается вместо входа,
 *    иначе войти было бы некуда;
 *  - login — обычный вход;
 *  - recover — сброс забытого пароля аварийным ключом из .env. Ссылка на
 *    него появляется, только если ключ задан, иначе вела бы в тупик.
 *
 * Пароль уходит отсюда один раз, в обмен на серверную сессию в
 * HttpOnly-куке — на клиенте он нигде не сохраняется.
 */
export function LoginScreen({ mode: initialMode, recoveryAvailable }: { mode: Mode; recoveryAvailable: boolean }) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<Mode>(initialMode);
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [recoveryKey, setRecoveryKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isSetup = mode === "setup";
  const isRecover = mode === "recover";

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);

    // Подтверждение проверяем на клиенте: серверу уходит один пароль, он о
    // втором поле не знает. Опечатка в новом пароле — самая обидная из
    // возможных, потому что запирает снаружи.
    if ((isSetup || isRecover) && password !== confirm) {
      setError(t("auth.errorPasswordsDiffer"));
      return;
    }

    setBusy(true);
    try {
      if (isSetup) await completeSetup(username, password);
      else if (isRecover) await recoverPassword(recoveryKey, password);
      else await login(username, password);

      // После сброса сессии нет — возвращаемся к форме входа.
      if (isRecover) {
        setMode("login");
        setPassword("");
        setConfirm("");
        setRecoveryKey("");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-0 px-4 py-8">
      <Card className="w-full max-w-sm">
        <CardContent className="flex flex-col items-center gap-6 p-6 pt-8 sm:p-8">
          <div className="flex flex-col items-center gap-1.5 text-center">
            <Logo size={40} />
            <span className="text-lg font-semibold tracking-tight text-text-primary">Aurum-Ex</span>
            <span className="text-xs text-text-muted">
              {isSetup ? t("auth.setupSubtitle") : isRecover ? t("auth.recoverSubtitle") : t("auth.subtitle")}
            </span>
          </div>

          <form onSubmit={handleSubmit} className="flex w-full flex-col gap-4">
            {!isRecover && (
              <div>
                <Label htmlFor="auth-username">{t("auth.usernameLabel")}</Label>
                <Input
                  id="auth-username"
                  name="username"
                  autoComplete="username"
                  autoFocus={!isSetup}
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  required
                />
              </div>
            )}

            {isRecover && (
              <div>
                <Label htmlFor="auth-recovery">{t("auth.recoveryKeyLabel")}</Label>
                <Input
                  id="auth-recovery"
                  name="recovery-key"
                  autoFocus
                  value={recoveryKey}
                  onChange={(event) => setRecoveryKey(event.target.value)}
                  required
                />
                <p className="mt-1 text-xs text-text-muted">{t("auth.recoveryKeyHint")}</p>
              </div>
            )}

            <div>
              <Label htmlFor="auth-password">
                {isSetup || isRecover ? t("auth.newPasswordLabel") : t("auth.passwordLabel")}
              </Label>
              <Input
                id="auth-password"
                name="password"
                type="password"
                autoComplete={isSetup || isRecover ? "new-password" : "current-password"}
                autoFocus={isSetup}
                minLength={isSetup || isRecover ? 8 : undefined}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
              {(isSetup || isRecover) && <p className="mt-1 text-xs text-text-muted">{t("auth.passwordHint")}</p>}
            </div>

            {(isSetup || isRecover) && (
              <div>
                <Label htmlFor="auth-confirm">{t("auth.confirmPasswordLabel")}</Label>
                <Input
                  id="auth-confirm"
                  name="confirm-password"
                  type="password"
                  autoComplete="new-password"
                  value={confirm}
                  onChange={(event) => setConfirm(event.target.value)}
                  required
                />
              </div>
            )}

            {error && <p className="text-sm text-danger">{error}</p>}

            <Button type="submit" className="w-full" disabled={busy}>
              {busy
                ? t("auth.submitting")
                : isSetup
                  ? t("auth.setupButton")
                  : isRecover
                    ? t("auth.recoverButton")
                    : t("auth.submitButton")}
            </Button>

            {mode === "login" && recoveryAvailable && (
              <button
                type="button"
                onClick={() => {
                  setMode("recover");
                  setError(null);
                  setPassword("");
                }}
                className="text-xs text-text-muted underline-offset-2 hover:underline"
              >
                {t("auth.forgotPassword")}
              </button>
            )}
            {mode === "recover" && (
              <button
                type="button"
                onClick={() => {
                  setMode("login");
                  setError(null);
                  setPassword("");
                }}
                className="text-xs text-text-muted underline-offset-2 hover:underline"
              >
                {t("auth.backToLogin")}
              </button>
            )}
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
