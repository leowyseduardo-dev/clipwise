import { useAccount } from "./AccountGate";
import type { Health } from "../lib/types";
import { IconChevronDown, IconSparkles, LogoMark } from "./icons";

export type AppView = "clips" | "live" | "tiktok" | "ai";

const NAV: { id: AppView; label: string }[] = [
  { id: "clips", label: "Estudio" },
  { id: "live", label: "Directos" },
  { id: "tiktok", label: "TikTok" },
  { id: "ai", label: "IA" },
];

function initials(name?: string, email?: string) {
  const source = (name || email || "C").trim();
  const parts = source.split(/\s+/).filter(Boolean);
  if (parts.length > 1) return (parts[0][0] + parts[1][0]).toUpperCase();
  return source.slice(0, 2).toUpperCase();
}

export function Header({
  health,
  healthError,
  view,
  onViewChange,
}: {
  health: Health | null;
  healthError: boolean;
  view: AppView;
  onViewChange: (view: AppView) => void;
}) {
  const account = useAccount();
  const nav = account.hosted ? NAV.filter((item) => item.id === "clips") : NAV;
  const ready = Boolean(health?.ffmpeg.available);
  const name = account.name?.trim() || account.email?.split("@")[0] || "Mi cuenta";

  function goCreate() {
    onViewChange("clips");
    window.setTimeout(() => {
      document.getElementById("crear")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 80);
  }

  return (
    <header className="sticky top-0 z-40 border-b border-slate-200/80 bg-white/80 backdrop-blur-2xl">
      <div className="mx-auto flex w-full max-w-[1240px] items-center justify-between gap-4 px-4 py-3 sm:px-6 lg:px-8">
        <button
          type="button"
          onClick={() => onViewChange("clips")}
          className="group flex shrink-0 items-center gap-3 text-left"
        >
          <LogoMark className="transition duration-300 group-hover:rotate-[-6deg]" />
          <span className="leading-none">
            <span className="block font-display text-[17px] font-bold tracking-tighter text-slate-900">
              Clipwise
              <span className="text-veru-ember">.</span>
            </span>
            <span className="mt-1 block text-[8px] font-semibold uppercase tracking-[0.34em] text-slate-400">
              Clip studio
            </span>
          </span>
        </button>

        {nav.length > 1 && (
          <nav className="hidden items-center gap-0.5 rounded-xl border border-slate-200 bg-slate-100/80 p-1 md:flex">
            {nav.map((item) => {
              const active = view === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => onViewChange(item.id)}
                  aria-pressed={active}
                  className={`nav-pill ${
                    active
                      ? "bg-white text-slate-900 shadow-sm"
                      : "text-slate-500 hover:bg-white/60 hover:text-slate-900"
                  }`}
                >
                  {item.label}
                </button>
              );
            })}
          </nav>
        )}

        <div className="flex shrink-0 items-center gap-2.5">
          <span className="hidden items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400 sm:inline-flex">
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                ready
                  ? "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.6)]"
                  : healthError
                    ? "bg-rose-500"
                    : "animate-pulse bg-amber-400"
              }`}
            />
            {ready ? "Motor listo" : healthError ? "Sin conexión" : "Conectando"}
          </span>

          <button
            type="button"
            onClick={goCreate}
            className="hidden items-center gap-1.5 rounded-xl border border-blue-200 bg-blue-50 px-3.5 py-2 text-[11px] font-semibold text-blue-700 transition hover:border-blue-300 hover:bg-blue-100 lg:inline-flex"
          >
            <IconSparkles size={13} />
            Crear clip
          </button>

          {account.signed_in && account.openAccount && (
            <button
              type="button"
              onClick={account.openAccount}
              className="flex items-center gap-2 rounded-full border border-slate-200 bg-white py-1 pl-1 pr-2.5 shadow-sm transition hover:border-slate-300 hover:shadow"
              aria-label="Abrir mi cuenta"
            >
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-blue-700 text-[10px] font-bold text-white">
                {initials(account.name, account.email)}
              </span>
              <span className="hidden text-left sm:block">
                <span className="block max-w-[8.5rem] truncate text-[11px] font-semibold leading-tight text-slate-800">
                  {name}
                </span>
                <span className="mt-0.5 block text-[8px] font-semibold uppercase tracking-[0.14em] text-slate-400">
                  {account.plan ?? "Starter"}
                </span>
              </span>
              <IconChevronDown size={13} className="hidden text-slate-400 sm:block" />
            </button>
          )}
        </div>
      </div>

      {nav.length > 1 && (
        <div className="border-t border-slate-100 px-3 py-2 md:hidden">
          <nav className="flex items-center justify-center gap-1 overflow-x-auto no-scrollbar">
            {nav.map((item) => {
              const active = view === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => onViewChange(item.id)}
                  aria-pressed={active}
                  className={`shrink-0 rounded-lg px-4 py-1.5 text-[11px] font-semibold transition ${
                    active
                      ? "bg-slate-900 text-white"
                      : "text-slate-500 hover:bg-slate-100 hover:text-slate-900"
                  }`}
                >
                  {item.label}
                </button>
              );
            })}
          </nav>
        </div>
      )}
    </header>
  );
}
