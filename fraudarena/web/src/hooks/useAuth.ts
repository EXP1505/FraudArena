// Owner: M4. Who is signed in. When the server has no GOOGLE_CLIENT_ID, `enabled` is false and nothing is gated.
import { useCallback, useEffect, useState } from "react";

export interface AuthUser { email: string; name: string; picture?: string | null }
export interface Auth { loading: boolean; enabled: boolean; user: AuthUser | null; refresh: () => Promise<void>; signOut: () => Promise<void> }

export function useAuth(): Auth {
  const [state, setState] = useState<{ loading: boolean; enabled: boolean; user: AuthUser | null }>({ loading: true, enabled: false, user: null });
  const refresh = useCallback(async () => {
    try {
      const r = await fetch("/api/auth/me");
      const j = await r.json();
      setState({ loading: false, enabled: !!j.enabled, user: j.user ?? null });
    } catch {
      setState({ loading: false, enabled: false, user: null });   // API offline: the pages show their own offline notice
    }
  }, []);
  useEffect(() => { refresh(); }, [refresh]);
  const signOut = useCallback(async () => {
    try { await fetch("/api/auth/logout", { method: "POST" }); } catch { /* cookie expires on its own */ }
    (window as any).google?.accounts?.id?.disableAutoSelect?.();
    await refresh();
  }, [refresh]);
  return { ...state, refresh, signOut };
}
