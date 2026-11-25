import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import type { ReactNode } from "react";

import {
  activatePaypalSubscription,
  cancelPaypalSubscription,
  getJson,
  sendJson,
  ApiError,
} from "../lib/api";
import { AccountPanel } from "./AccountPanel";
import type { Account, AdminOverview, AdminTeam } from "./AccountPanel";
import { AuthScreen } from "./AuthScreen";
import { MarketingPage } from "./MarketingPage";
import { IconAlert, IconLoader, LogoMark } from "./icons";

type AccountContextValue = Account & { openAccount?: () => void };

const Context = createContext<AccountContextValue>({ hosted: false });
export const useAccount = () => useContext(Context);

export function AccountGate({ children }: { children: ReactNode }) {
  const [a, setA] = useState<Account | null>(null);
  const [adminData, setAdminData] = useState<AdminOverview | null>(null);
  const [adminTeams, setAdminTeams] = useState<AdminTeam[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);
  const [authMode, setAuthMode] = useState<"login" | "register" | null>(null);

  const refresh = useCallback(async () => {
    try {
      setA(await getJson<Account>("/api/account"));
      setError("");
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) {
        setA({ hosted: true, signed_in: false });
      } else {
        setError(caught instanceof Error ? caught.message : "No se pudo conectar.");
      }
    }
  }, []);

  const loadAdmin = useCallback(async () => {
    try {
      setAdminData(await getJson<AdminOverview>("/api/admin/overview"));
    } catch {
      setAdminData(null);
    }
  }, []);

  const loadAdminTeams = useCallback(async () => {
    try {
      const data = await getJson<{ teams: AdminTeam[] }>("/api/admin/teams");
      setAdminTeams(data.teams ?? []);
    } catch {
      setAdminTeams([]);
    }
  }, []);

  useEffect(() => {
    void refresh();
    window.addEventListener("focus", refresh);
    return () => window.removeEventListener("focus", refresh);
  }, [refresh]);

  useEffect(() => {
    if (a?.admin) {
      void loadAdmin();
      void loadAdminTeams();
    }
  }, [a?.admin, loadAdmin, loadAdminTeams]);

  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await fn();
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "No se pudo completar.");
    } finally {
      setBusy(false);
    }
  }

  async function activatePaypal(subscriptionId: string) {
    setBusy(true);
    setError("");
    try {
      await activatePaypalSubscription(subscriptionId);
      await refresh();
    } catch (caught) {
      const message =
        caught instanceof Error
          ? caught.message
          : "No se pudo activar el plan.";
      setError(message);
      throw caught;
    } finally {
      setBusy(false);
    }
  }

  async function cancelPaypal() {
    setBusy(true);
    setError("");
    try {
      await cancelPaypalSubscription();
      await refresh();
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "No se pudo cancelar la suscripción.",
      );
      throw caught;
    } finally {
      setBusy(false);
    }
  }

  async function adminResetLink(email: string): Promise<string> {
    setBusy(true);
    setError("");
    try {
      const data = await sendJson<{ url: string }>(
        "/api/admin/reset-link?email=" + encodeURIComponent(email),
        "POST",
      );
      return data.url;
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "No se pudo generar el enlace.",
      );
      throw caught;
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    await act(() => sendJson("/api/account/logout", "POST"));
    setPanelOpen(false);
    setAuthMode(null);
  }

  if (!a) {
    return (
      <main className="auth-canvas flex min-h-screen flex-col items-center justify-center px-6">
        <div className="auth-rise flex flex-col items-center text-center">
          <LogoMark className="h-12 w-12 rounded-2xl" />
          <p className="mt-5 font-display text-xl font-semibold tracking-tight text-slate-900">
            Abriendo Clipwise<span className="text-veru-ember">.</span>
          </p>
          {error ? (
            <div className="mt-4 max-w-sm rounded-2xl border border-rose-200 bg-white px-5 py-4 shadow-panel">
              <p className="flex items-center justify-center gap-2 text-[12px] font-medium text-rose-600">
                <IconAlert size={15} />
                {error}
              </p>
              <button type="button" className="button-ghost mt-3" onClick={() => void refresh()}>
                Reintentar
              </button>
            </div>
          ) : (
            <p className="mt-2 inline-flex items-center gap-2 text-[11px] text-slate-400">
              <IconLoader size={13} className="animate-spin" />
              Preparando tu estudio
            </p>
          )}
        </div>
      </main>
    );
  }

  if (!a.hosted) return <>{children}</>;

  const resetLink =
    typeof window !== "undefined" &&
    new URLSearchParams(window.location.search).has("reset");

  // A reset link must work even when another tab is already signed in.
  if (resetLink) {
    return <AuthScreen onAuthenticated={refresh} />;
  }

  if (!a.signed_in) {
    if (!authMode) {
      return <MarketingPage onStart={setAuthMode} />;
    }
    return (
      <AuthScreen
        initialMode={authMode}
        onBack={() => setAuthMode(null)}
        onAuthenticated={refresh}
      />
    );
  }

  return (
    <Context.Provider value={{ ...a, openAccount: () => setPanelOpen(true) }}>
      <div key={a.team}>{children}</div>
      {panelOpen && (
        <AccountPanel
          account={a}
          adminData={adminData}
          adminTeams={adminTeams}
          busy={busy}
          error={error}
          onClose={() => setPanelOpen(false)}
          onRefresh={async () => {
            await refresh();
            if (a.admin) {
              await loadAdmin();
              await loadAdminTeams();
            }
          }}
          onLogout={logout}
          onActivatePaypal={activatePaypal}
          onCancelPaypal={cancelPaypal}
          onSetPlan={(team, plan) =>
            act(async () => {
              await sendJson("/api/admin/plan", "POST", { team, plan });
              await loadAdmin();
              await loadAdminTeams();
            })
          }
          onAddMember={(email, role) =>
            act(() => sendJson("/api/account/member", "PUT", { email, role }))
          }
          onRemoveMember={(email) =>
            act(() =>
              sendJson("/api/account/member?email=" + encodeURIComponent(email), "DELETE"),
            )
          }
          onSwitchTeam={(teamId) =>
            act(async () => {
              await sendJson("/api/account/team/" + teamId, "PUT");
              window.history.replaceState({}, "", "/");
            })
          }
          onSuspend={(email) =>
            act(async () => {
              await sendJson(
                "/api/admin/suspend?email=" + encodeURIComponent(email),
                "POST",
              );
              await loadAdmin();
            })
          }
          onResetLink={adminResetLink}
        />
      )}
    </Context.Provider>
  );
}
