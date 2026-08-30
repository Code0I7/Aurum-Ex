import { type ReactNode, useEffect, useState } from "react";
import { Logo } from "@/components/layout/Logo";
import { LoginScreen } from "@/components/auth/LoginScreen";
import { checkCredentials, useAuthHeader } from "@/lib/auth";

type Probe = "checking" | "required" | "not-required";

/** Wraps the whole app. Renders the login screen only when this instance
 * actually has Basic Auth turned on (AURUM_BASIC_AUTH_USER/PASSWORD in
 * .env, see frontend/docker-entrypoint.d/20-basic-auth.sh) — most installs
 * don't, and this must never force a login screen on those. When stored
 * credentials go stale (password changed, or auth was just turned on) the
 * 401 handler in api/client.ts clears them, useAuthHeader() picks that up
 * reactively, and this falls back to the login screen on its own. */
export function LoginGate({ children }: { children: ReactNode }) {
  const authHeader = useAuthHeader();
  const [probe, setProbe] = useState<Probe>(authHeader ? "not-required" : "checking");

  useEffect(() => {
    if (authHeader) {
      setProbe("not-required");
      return;
    }
    let cancelled = false;
    checkCredentials(null).then((result) => {
      if (cancelled) return;
      // A network/backend error here isn't an auth problem — don't block
      // the user behind a login screen for an unrelated outage, let the
      // app's own per-page error states (e.g. dashboard.errorLoading) explain it.
      setProbe(result === "unauthorized" ? "required" : "not-required");
    });
    return () => {
      cancelled = true;
    };
  }, [authHeader]);

  if (probe === "checking") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface-0">
        <Logo size={40} className="animate-pulse" />
      </div>
    );
  }

  if (probe === "required" && !authHeader) {
    return <LoginScreen />;
  }

  return <>{children}</>;
}
