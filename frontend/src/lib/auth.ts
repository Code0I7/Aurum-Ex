import { useSyncExternalStore } from "react";

/**
 * Client-side mirror of the HTTP Basic Auth credentials Aurum's own login
 * screen collects (see components/auth/LoginScreen.tsx), so every fetch can
 * attach `Authorization` itself instead of relying on the browser's own
 * unstyled Basic Auth prompt. nginx's `auth_basic` (see
 * frontend/docker-entrypoint.d/20-basic-auth.sh) is still the actual gate —
 * this only avoids ever triggering that native prompt, by never letting an
 * unauthenticated request happen without us attaching the header ourselves.
 *
 * Kept in sessionStorage, not localStorage: closing the tab signs the user
 * back out, which matters more for a finance app than staying logged in
 * across days.
 */
const STORAGE_KEY = "aurum:basicAuth";

function readStored(): string | null {
  try {
    return sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

let currentHeader: string | null = readStored();
const listeners = new Set<() => void>();

function notify(): void {
  listeners.forEach((listener) => listener());
}

export function getAuthHeader(): string | null {
  return currentHeader;
}

// btoa() only handles Latin1 — the UI is bilingual RU/EN, so a Cyrillic
// password has to survive this, not just ASCII ones.
function encodeUtf8Base64(value: string): string {
  const bytes = new TextEncoder().encode(value);
  let binary = "";
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return btoa(binary);
}

export function buildBasicAuthHeader(username: string, password: string): string {
  return `Basic ${encodeUtf8Base64(`${username}:${password}`)}`;
}

export function setCredentials(username: string, password: string): void {
  currentHeader = buildBasicAuthHeader(username, password);
  try {
    sessionStorage.setItem(STORAGE_KEY, currentHeader);
  } catch {
    // sessionStorage unavailable (private browsing, storage disabled) — the
    // header still works for the rest of this tab's life via the in-memory
    // variable above, it just won't survive a refresh.
  }
  notify();
}

/** Called on any 401 response (see api/client.ts) so a revoked or changed
 * password falls back to the login screen instead of every request failing
 * silently forever. */
export function clearCredentials(): void {
  if (currentHeader === null) return;
  currentHeader = null;
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore — nothing to clean up if storage was never usable
  }
  notify();
}

export type CredentialCheck = "ok" | "unauthorized" | "unreachable";

// A request with NO Authorization header at all, hitting an endpoint that
// replies 401 + WWW-Authenticate: Basic, is exactly what makes some
// browsers pop their own native Basic Auth dialog even for a plain
// fetch() — the one thing this whole login screen exists to avoid. A
// request that already carries *some* Authorization header, even a wrong
// one, never triggers that. So LoginGate's "is auth even required?" probe
// (called with header=null) uses this fixed placeholder instead of
// omitting the header — it's guaranteed wrong, which is exactly what's
// needed to tell "not configured" (200, header ignored) apart from
// "configured, please log in" (401).
const PROBE_HEADER = `Basic ${btoa("__aurum_probe__:__aurum_probe__")}`;

/** Hits a lightweight, always-protected endpoint with the given header (or
 * none) to find out whether Basic Auth is required/satisfied. Used both to
 * skip the login screen entirely when this instance has no auth configured
 * (see LoginGate.tsx), and to validate a login attempt before saving it
 * (see LoginScreen.tsx). */
export async function checkCredentials(header: string | null): Promise<CredentialCheck> {
  try {
    const response = await fetch("/api/accounts", {
      headers: { Authorization: header ?? PROBE_HEADER },
    });
    return response.status === 401 ? "unauthorized" : "ok";
  } catch {
    return "unreachable";
  }
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useAuthHeader(): string | null {
  return useSyncExternalStore(subscribe, () => currentHeader);
}
