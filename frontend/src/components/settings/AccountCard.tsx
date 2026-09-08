import { type FormEvent, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input, Label } from "@/components/ui/Input";
import { changePassword, logout, useAuthState } from "@/lib/auth";
import { useTranslation } from "@/lib/i18n";

/**
 * Учётная запись: кто вошёл, выход и смена пароля.
 *
 * Форма смены свёрнута по умолчанию — в настройки заходят менять валюту и
 * пороги оповещений, а не пароль, и разворачивать её каждый раз незачем.
 * Текущий пароль обязателен: домохозяйство сидит под одной учёткой, и
 * защита тут не от злоумышленника, а от случайности.
 */
export function AccountCard() {
  const { t } = useTranslation();
  const auth = useAuthState();
  const [open, setOpen] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (newPassword !== confirm) {
      setError(t("auth.errorPasswordsDiffer"));
      return;
    }
    setBusy(true);
    try {
      // Смена обрывает все сессии, включая эту, — приложение само покажет
      // экран входа, как только состояние обновится.
      await changePassword(currentPassword, newPassword);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("settings.account")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-text-muted">
            {t("auth.signedInAs")} <span className="font-medium text-text-primary">{auth?.username ?? "—"}</span>
          </p>
          <Button variant="secondary" onClick={() => void logout()}>
            {t("auth.signOut")}
          </Button>
        </div>

        {!open ? (
          <button
            type="button"
            onClick={() => setOpen(true)}
            className="text-sm text-text-muted underline-offset-2 hover:underline"
          >
            {t("auth.changePassword")}
          </button>
        ) : (
          <form onSubmit={handleSubmit} className="flex max-w-sm flex-col gap-3 border-t border-border pt-4">
            <div>
              <Label htmlFor="settings-current-password">{t("auth.currentPasswordLabel")}</Label>
              <Input
                id="settings-current-password"
                type="password"
                autoComplete="current-password"
                value={currentPassword}
                onChange={(event) => setCurrentPassword(event.target.value)}
                required
              />
            </div>
            <div>
              <Label htmlFor="settings-new-password">{t("auth.newPasswordLabel")}</Label>
              <Input
                id="settings-new-password"
                type="password"
                autoComplete="new-password"
                minLength={8}
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
                required
              />
            </div>
            <div>
              <Label htmlFor="settings-confirm-password">{t("auth.confirmPasswordLabel")}</Label>
              <Input
                id="settings-confirm-password"
                type="password"
                autoComplete="new-password"
                value={confirm}
                onChange={(event) => setConfirm(event.target.value)}
                required
              />
            </div>

            <p className="text-xs text-text-muted">{t("auth.changePasswordHint")}</p>
            {error && <p className="text-sm text-danger">{error}</p>}

            <div className="flex flex-wrap gap-2">
              <Button type="submit" disabled={busy}>
                {busy ? t("auth.submitting") : t("auth.changePassword")}
              </Button>
              <Button type="button" variant="secondary" onClick={() => setOpen(false)} disabled={busy}>
                {t("common.cancel")}
              </Button>
            </div>
          </form>
        )}
      </CardContent>
    </Card>
  );
}
