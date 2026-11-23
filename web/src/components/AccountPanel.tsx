import { useState } from "react";
import type { FormEvent } from "react";

import { PAYPAL_SUPPORT_EMAIL, paypalLink } from "../lib/paypal";
import {
  IconAlert,
  IconArrowRight,
  IconBolt,
  IconCheck,
  IconFilm,
  IconLoader,
  IconMail,
  IconSettings,
  IconShield,
  IconSparkles,
  IconUser,
  IconX,
} from "./icons";

export type Account = {
  hosted: boolean;
  signed_in?: boolean;
  email?: string;
  name?: string;
  team?: string;
  plan?: string;
  used?: number;
  limit?: number;
  role?: string;
  billing?: boolean;
  paypal_me?: string;
  teams?: { id: string; name: string }[];
  members?: { email: string; role: string }[];
  plans?: Record<string, number[]>;
  admin?: boolean;
};

export type AdminTeam = {
  id: string;
  name: string;
  plan: string;
  owner: string;
  used: number;
  members: number;
};

export type AdminOverview = {
  users: number;
  teams: number;
  by_plan: Record<string, number>;
  clips_this_month: number;
  plans: Record<string, number[]>;
};

type Tab = "resumen" | "equipo" | "plan" | "admin";

const PLAN_META: Record<
  string,
  { price: number; tagline: string; features: string[]; popular?: boolean }
> = {
  Starter: {
    price: 0,
    tagline: "Para probar el flujo completo",
    features: ["2 clips al día", "20 clips al mes", "1 proyecto a la vez", "720p con marca de agua"],
  },
  Creator: {
    price: 5,
    tagline: "El más recomendado",
    features: [
      "120 clips al mes",
      "1080p sin marca de agua",
      "3 proyectos a la vez",
      "2 plazas de equipo",
    ],
    popular: true,
  },
  Studio: {
    price: 10,
    tagline: "Para producir a escala",
    features: [
      "400 clips al mes",
      "Máxima prioridad de render",
      "8 proyectos a la vez",
      "5 plazas de equipo",
    ],
  },
};

function initials(name?: string, email?: string) {
  const source = (name || email || "C").trim();
  const parts = source.split(/\s+/).filter(Boolean);
  if (parts.length > 1) return (parts[0][0] + parts[1][0]).toUpperCase();
  return source.slice(0, 2).toUpperCase();
}

function displayName(account: Account) {
  if (account.name?.trim()) return account.name.trim();
  return account.email?.split("@")[0] ?? "Tu cuenta";
}

export function AccountPanel({
  account,
  adminData,
  adminTeams,
  busy,
  error,
  onClose,
  onRefresh,
  onLogout,
  onBilling,
  onSetPlan,
  onAddMember,
  onRemoveMember,
  onSwitchTeam,
  onSuspend,
}: {
  account: Account;
  adminData: AdminOverview | null;
  adminTeams: AdminTeam[];
  busy: boolean;
  error: string;
  onClose: () => void;
  onRefresh: () => Promise<void>;
  onLogout: () => Promise<void>;
  onBilling: (plan: string) => Promise<void>;
  onSetPlan: (team: string, plan: string) => Promise<void>;
  onAddMember: (email: string, role: string) => Promise<void>;
  onRemoveMember: (email: string) => Promise<void>;
  onSwitchTeam: (teamId: string) => Promise<void>;
  onSuspend: (email: string) => Promise<void>;
}) {
  const [tab, setTab] = useState<Tab>("resumen");
  const [member, setMember] = useState("");
  const [memberRole, setMemberRole] = useState("editor");
  const [suspendEmail, setSuspendEmail] = useState("");
  const [planDrafts, setPlanDrafts] = useState<Record<string, string>>({});

  const plan = account.plan ?? "Starter";
  const paypalMe = (account.paypal_me ?? "").trim();
  const manualPaypal = Boolean(paypalMe);
  const used = account.used ?? 0;
  const limit = account.limit ?? 0;
  const remaining = Math.max(0, limit - used);
  const percent = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0;
  const meta = PLAN_META[plan] ?? PLAN_META.Starter;
  const seats = account.plans?.[plan]?.[1] ?? 1;
  const canManage = account.role === "owner";

  const tabs: { id: Tab; label: string }[] = [
    { id: "resumen", label: "Resumen" },
    { id: "equipo", label: "Equipo" },
    { id: "plan", label: "Plan" },
    ...(account.admin ? [{ id: "admin" as Tab, label: "Admin" }] : []),
  ];

  function submitMember(event: FormEvent) {
    event.preventDefault();
    if (!member.trim()) return;
    void onAddMember(member.trim(), memberRole).then(() => setMember(""));
  }

  function submitSuspend(event: FormEvent) {
    event.preventDefault();
    const email = suspendEmail.trim();
    if (!email) return;
    if (!window.confirm(`¿Cerrar todas las sesiones de ${email}?`)) return;
    void onSuspend(email).then(() => setSuspendEmail(""));
  }

  return (
    <div
      className="account-backdrop fixed inset-0 z-[60] flex justify-end bg-slate-950/40 backdrop-blur-sm"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <aside
        className="account-sheet relative flex h-full w-full max-w-[460px] flex-col overflow-y-auto bg-white shadow-[-24px_0_80px_-40px_rgba(15,23,42,0.5)]"
        role="dialog"
        aria-modal="true"
        aria-label="Mi cuenta"
      >
        <div className="relative overflow-hidden border-b border-slate-100 bg-gradient-to-br from-blue-600 to-blue-800 px-6 pb-5 pt-6 text-white">
          <div className="pointer-events-none absolute -right-10 -top-16 h-44 w-44 rounded-full bg-white/10 blur-2xl" />
          <div className="relative flex items-start justify-between gap-3">
            <div className="flex items-center gap-3">
              <span className="flex h-12 w-12 items-center justify-center rounded-2xl border border-white/20 bg-white/15 font-display text-base font-bold text-white backdrop-blur">
                {initials(account.name, account.email)}
              </span>
              <div className="min-w-0">
                <p className="truncate font-display text-lg font-semibold tracking-tight text-white">
                  {displayName(account)}
                </p>
                <p className="truncate text-[11px] text-blue-100/80">{account.email}</p>
              </div>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="rounded-xl border border-white/15 bg-white/10 p-2 text-white/80 transition hover:bg-white/20 hover:text-white"
              aria-label="Cerrar mi cuenta"
            >
              <IconX size={17} />
            </button>
          </div>
          <div className="relative mt-4 flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-white/20 bg-white/15 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-white">
              <IconSparkles size={11} />
              Plan {plan}
            </span>
            <span className="rounded-full border border-white/15 bg-slate-950/20 px-2.5 py-1 text-[10px] font-medium text-blue-100/80">
              {account.role === "owner" ? "Propietario" : account.role === "editor" ? "Editor" : "Lectura"}
            </span>
          </div>
        </div>

        <div className="border-b border-slate-100 px-4 pt-3">
          <div className="flex gap-1 overflow-x-auto no-scrollbar">
            {tabs.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setTab(item.id)}
                aria-pressed={tab === item.id}
                className={`shrink-0 rounded-t-lg border-b-2 px-3.5 py-2.5 text-[11px] font-semibold transition ${
                  tab === item.id
                    ? "border-veru-ember text-slate-900"
                    : "border-transparent text-slate-400 hover:text-slate-700"
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 space-y-5 px-5 py-5">
          {error && (
            <div
              role="alert"
              className="flex items-start gap-2.5 rounded-xl border border-rose-200 bg-rose-50 px-3.5 py-3 text-[12px] font-medium leading-relaxed text-rose-700"
            >
              <IconAlert size={15} className="mt-0.5 shrink-0" />
              {error}
            </div>
          )}

          {tab === "resumen" && (
            <>
              <section className="rounded-2xl border border-slate-200 bg-slate-50/70 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-400">
                      Clips este mes
                    </p>
                    <p className="mt-1 font-display text-2xl font-semibold tracking-tight text-slate-900">
                      {used} <span className="text-base font-medium text-slate-400">/ {limit}</span>
                    </p>
                  </div>
                  <span className="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[10px] font-semibold text-slate-500">
                    {remaining} restantes
                  </span>
                </div>
                <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-200">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${
                      percent >= 100 ? "bg-rose-500" : percent >= 80 ? "bg-amber-400" : "bg-veru-ember"
                    }`}
                    style={{ width: `${percent}%` }}
                  />
                </div>
                <p className="mt-2 text-[10px] leading-relaxed text-slate-400">
                  {plan === "Starter"
                    ? "El plan Starter incluye 2 clips al día y 20 al mes. El contador diario se reinicia a medianoche UTC."
                    : "El contador se reinicia con tu ciclo de facturación mensual."}
                </p>
              </section>

              <section className="space-y-2">
                <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-400">
                  Cuenta
                </p>
                <div className="rounded-2xl border border-slate-200">
                  <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
                    <span className="inline-flex items-center gap-2 text-[12px] text-slate-500">
                      <IconUser size={14} /> Nombre
                    </span>
                    <span className="truncate text-[12px] font-semibold text-slate-800">
                      {displayName(account)}
                    </span>
                  </div>
                  <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
                    <span className="inline-flex items-center gap-2 text-[12px] text-slate-500">
                      <IconMail size={14} /> Correo
                    </span>
                    <span className="truncate text-[12px] font-semibold text-slate-800">
                      {account.email}
                    </span>
                  </div>
                  <div className="flex items-center justify-between gap-3 px-4 py-3">
                    <span className="inline-flex items-center gap-2 text-[12px] text-slate-500">
                      <IconFilm size={14} /> Plan
                    </span>
                    <span className="text-[12px] font-semibold text-slate-800">
                      {plan} · ${meta.price}/mes
                    </span>
                  </div>
                </div>
              </section>

              <div className="grid gap-2">
                <button
                  type="button"
                  className="button-primary w-full"
                  onClick={() => {
                    onClose();
                    window.setTimeout(() => {
                      document
                        .getElementById("crear")
                        ?.scrollIntoView({ behavior: "smooth", block: "start" });
                    }, 120);
                  }}
                >
                  <IconBolt size={15} />
                  Crear clips
                </button>
                <button
                  type="button"
                  className="button-ghost w-full"
                  onClick={() => setTab("plan")}
                >
                  <IconSettings size={14} />
                  Gestionar plan y facturación
                </button>
                <button
                  type="button"
                  className="button-ghost w-full text-rose-600 hover:border-rose-200 hover:bg-rose-50 hover:text-rose-700"
                  disabled={busy}
                  onClick={() => void onLogout()}
                >
                  Cerrar sesión
                </button>
              </div>
            </>
          )}

          {tab === "equipo" && (
            <>
              <section className="rounded-2xl border border-slate-200 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-[12px] font-semibold text-slate-800">Equipo actual</p>
                    <p className="mt-0.5 text-[10px] text-slate-400">
                      {account.teams?.find((team) => team.id === account.team)?.name ?? "Mi espacio"}
                    </p>
                  </div>
                  <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[10px] font-semibold text-slate-500">
                    {account.members?.length ?? 1} / {seats} plazas
                  </span>
                </div>
                {(account.teams?.length ?? 0) > 1 && (
                  <select
                    className="field mt-3"
                    value={account.team}
                    onChange={(event) => void onSwitchTeam(event.target.value)}
                    aria-label="Cambiar de equipo"
                  >
                    {account.teams?.map((team) => (
                      <option key={team.id} value={team.id}>
                        {team.name}
                      </option>
                    ))}
                  </select>
                )}
              </section>

              <section>
                <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-400">
                  Miembros
                </p>
                <div className="divide-y divide-slate-100 rounded-2xl border border-slate-200">
                  {account.members?.map((memberItem) => (
                    <div
                      key={memberItem.email}
                      className="flex items-center justify-between gap-3 px-4 py-3"
                    >
                      <div className="flex min-w-0 items-center gap-2.5">
                        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-100 text-[10px] font-bold text-slate-600">
                          {initials(undefined, memberItem.email)}
                        </span>
                        <div className="min-w-0">
                          <p className="truncate text-[12px] font-semibold text-slate-800">
                            {memberItem.email}
                          </p>
                          <p className="text-[10px] capitalize text-slate-400">
                            {memberItem.role === "owner" ? "Propietario" : memberItem.role}
                          </p>
                        </div>
                      </div>
                      {account.role === "owner" && memberItem.role !== "owner" && (
                        <button
                          type="button"
                          className="button-ghost px-2.5 py-1 text-[10px]"
                          disabled={busy}
                          onClick={() => void onRemoveMember(memberItem.email)}
                        >
                          Quitar
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </section>

              {account.role === "owner" && (
                <form onSubmit={submitMember} className="space-y-2.5 rounded-2xl border border-slate-200 p-4">
                  <p className="text-[12px] font-semibold text-slate-800">Añadir miembro</p>
                  <p className="text-[10px] leading-relaxed text-slate-400">
                    La persona debe tener una cuenta de Clipwise registrada.
                  </p>
                  <input
                    className="field"
                    type="email"
                    placeholder="correo@ejemplo.com"
                    value={member}
                    onChange={(event) => setMember(event.target.value)}
                    aria-label="Correo del nuevo miembro"
                  />
                  <div className="flex gap-2">
                    <select
                      className="field"
                      value={memberRole}
                      onChange={(event) => setMemberRole(event.target.value)}
                      aria-label="Rol del nuevo miembro"
                    >
                      <option value="editor">Editor</option>
                      <option value="viewer">Lectura</option>
                    </select>
                    <button
                      type="submit"
                      className="button-primary shrink-0 px-4"
                      disabled={busy || !member.trim()}
                    >
                      {busy ? <IconLoader size={15} className="animate-spin" /> : "Añadir"}
                    </button>
                  </div>
                </form>
              )}
            </>
          )}

          {tab === "plan" && (
            <>
              <section className="rounded-2xl border border-blue-200 bg-blue-50/60 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-blue-600">
                      Plan actual
                    </p>
                    <p className="mt-1 font-display text-xl font-semibold tracking-tight text-slate-900">
                      {plan}
                    </p>
                    <p className="mt-1 text-[11px] text-slate-500">{meta.tagline}</p>
                  </div>
                  <span className="rounded-full border border-blue-200 bg-white px-2.5 py-1 text-[10px] font-semibold text-blue-700">
                    ${meta.price}/mes
                  </span>
                </div>
              </section>

              <div className="space-y-2.5">
                {Object.entries(account.plans ?? {}).map(([name, limits]) => {
                  const info = PLAN_META[name] ?? PLAN_META.Starter;
                  const current = name === plan;
                  const paid = account.plan !== "Starter";
                  return (
                    <div
                      key={name}
                      className={`rounded-2xl border p-4 transition ${
                        current
                          ? "border-blue-300 bg-blue-50/50"
                          : "border-slate-200 bg-white hover:border-slate-300"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="flex items-center gap-2">
                            <p className="text-[13px] font-semibold text-slate-900">{name}</p>
                            {info.popular && (
                              <span className="rounded-full bg-blue-600 px-2 py-0.5 text-[9px] font-bold uppercase tracking-[0.08em] text-white">
                                Popular
                              </span>
                            )}
                            {current && (
                              <span className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[9px] font-bold uppercase tracking-[0.08em] text-emerald-700">
                                <IconCheck size={10} /> Actual
                              </span>
                            )}
                          </div>
                          <p className="mt-0.5 text-[10px] text-slate-400">{info.tagline}</p>
                        </div>
                        <p className="shrink-0 font-display text-lg font-semibold tracking-tight text-slate-900">
                          {info.price === 0 ? "Gratis" : `$${info.price}`}
                          {info.price > 0 && (
                            <span className="text-[10px] font-medium text-slate-400">/mes</span>
                          )}
                        </p>
                      </div>
                      <ul className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1.5">
                        {info.features.map((feature) => (
                          <li
                            key={feature}
                            className="flex items-start gap-1.5 text-[10px] leading-relaxed text-slate-500"
                          >
                            <IconCheck size={11} className="mt-0.5 shrink-0 text-blue-500" />
                            {feature}
                          </li>
                        ))}
                      </ul>
                      <div className="mt-3 flex items-center justify-between gap-3">
                        <span className="text-[9px] uppercase tracking-[0.1em] text-slate-400">
                          {limits[0]} clips/mes · {limits[2]} proyectos a la vez
                        </span>
                        {!current &&
                          (manualPaypal ? (
                            canManage ? (
                              plan === "Starter" ? (
                                <a
                                  href={paypalLink(paypalMe, info.price)}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="button-primary px-3 py-1.5 text-[10px]"
                                >
                                  Pagar ${info.price} con PayPal
                                  <IconArrowRight size={12} />
                                </a>
                              ) : (
                                <a
                                  href={`mailto:${PAYPAL_SUPPORT_EMAIL}?subject=${encodeURIComponent(
                                    `Cambio de plan a ${name}`,
                                  )}&body=${encodeURIComponent(
                                    `Hola, quiero cambiar el plan del equipo ${
                                      account.team ?? ""
                                    } de ${plan} a ${name}.`,
                                  )}`}
                                  className="button-ghost px-3 py-1.5 text-[10px]"
                                >
                                  Solicitar cambio
                                  <IconArrowRight size={12} />
                                </a>
                              )
                            ) : (
                              <span className="text-[9px] text-slate-400">
                                Solo el propietario
                              </span>
                            )
                          ) : (
                            <button
                              type="button"
                              className="button-ghost px-3 py-1.5 text-[10px]"
                              disabled={busy || !account.billing || !canManage}
                              onClick={() => void onBilling(paid ? "portal" : name)}
                              title={
                                !canManage
                                  ? "Solo el propietario puede cambiar el plan."
                                  : !account.billing
                                    ? "La facturación no está configurada en el servidor."
                                    : undefined
                              }
                            >
                              {busy ? (
                                <IconLoader size={12} className="animate-spin" />
                              ) : paid ? (
                                "Gestionar suscripción"
                              ) : (
                                "Elegir plan"
                              )}
                              <IconArrowRight size={12} />
                            </button>
                          ))}
                      </div>
                    </div>
                  );
                })}
              </div>

              {manualPaypal ? (
                <p className="flex items-start gap-2 rounded-xl border border-blue-200 bg-blue-50 px-3.5 py-3 text-[10px] leading-relaxed text-blue-700">
                  <IconCheck size={13} className="mt-0.5 shrink-0" />
                  Pago manual con PayPal. Después de pagar, un administrador activa tu
                  plan. Usa el mismo correo de tu cuenta y, si tienes dudas, escribe a{" "}
                  {PAYPAL_SUPPORT_EMAIL}.
                </p>
              ) : !account.billing ? (
                <p className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3.5 py-3 text-[10px] leading-relaxed text-amber-700">
                  <IconAlert size={13} className="mt-0.5 shrink-0" />
                  Los pagos manuales con PayPal aún no están configurados. Escribe a{" "}
                  {PAYPAL_SUPPORT_EMAIL} para activar tu plan.
                </p>
              ) : null}

              {account.billing && !manualPaypal && account.plan !== "Starter" && canManage && (
                <button
                  type="button"
                  className="button-ghost w-full"
                  disabled={busy}
                  onClick={() => void onBilling("portal")}
                >
                  <IconSettings size={14} />
                  Abrir portal de facturación
                </button>
              )}
            </>
          )}

          {tab === "admin" && account.admin && (
            <>
              <section className="grid grid-cols-2 gap-2.5">
                {[
                  { label: "Usuarios", value: adminData?.users ?? 0 },
                  { label: "Equipos", value: adminData?.teams ?? 0 },
                  { label: "Clips este mes", value: adminData?.clips_this_month ?? 0 },
                  {
                    label: "Planes activos",
                    value: Object.keys(adminData?.by_plan ?? {}).length,
                  },
                ].map((stat) => (
                  <div
                    key={stat.label}
                    className="rounded-2xl border border-slate-200 bg-slate-50/60 p-3.5"
                  >
                    <p className="text-[9px] font-semibold uppercase tracking-[0.14em] text-slate-400">
                      {stat.label}
                    </p>
                    <p className="mt-1 font-display text-xl font-semibold tracking-tight text-slate-900">
                      {stat.value}
                    </p>
                  </div>
                ))}
              </section>

              <section className="rounded-2xl border border-slate-200 p-4">
                <p className="text-[12px] font-semibold text-slate-800">Usuarios por plan</p>
                <div className="mt-2 space-y-1.5">
                  {Object.entries(adminData?.by_plan ?? {}).map(([name, count]) => (
                    <div key={name} className="flex items-center justify-between text-[11px]">
                      <span className="text-slate-500">{name}</span>
                      <span className="font-semibold text-slate-800">{count}</span>
                    </div>
                  ))}
                </div>
                <button
                  type="button"
                  className="button-ghost mt-3 w-full"
                  onClick={() => void onRefresh()}
                >
                  <IconLoader size={13} />
                  Actualizar datos
                </button>
              </section>

              <section className="rounded-2xl border border-slate-200 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-[12px] font-semibold text-slate-800">
                      Activar plan manual
                    </p>
                    <p className="mt-0.5 text-[10px] leading-relaxed text-slate-400">
                      Para pagos recibidos por PayPal. El cambio se aplica al instante.
                    </p>
                  </div>
                  <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[9px] font-semibold text-slate-500">
                    {adminTeams.length} equipos
                  </span>
                </div>
                <div className="mt-3 max-h-80 space-y-2 overflow-y-auto pr-1">
                  {adminTeams.map((team) => {
                    const draft = planDrafts[team.id] ?? team.plan;
                    return (
                      <div
                        key={team.id}
                        className="rounded-xl border border-slate-200 bg-slate-50/40 p-3"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <p className="truncate text-[11px] font-semibold text-slate-800">
                              {team.name}
                            </p>
                            <p className="truncate text-[10px] text-slate-400">
                              {team.owner || "Sin propietario"}
                            </p>
                          </div>
                          <span className="shrink-0 rounded-full border border-blue-200 bg-blue-50 px-2 py-0.5 text-[9px] font-bold uppercase tracking-[0.08em] text-blue-700">
                            {team.plan}
                          </span>
                        </div>
                        <div className="mt-2 flex gap-2">
                          <select
                            className="field px-2.5 py-1.5 text-[11px]"
                            value={draft}
                            onChange={(event) =>
                              setPlanDrafts((current) => ({
                                ...current,
                                [team.id]: event.target.value,
                              }))
                            }
                            aria-label={`Plan de ${team.name}`}
                          >
                            {Object.keys(account.plans ?? {}).map((name) => (
                              <option key={name} value={name}>
                                {name}
                              </option>
                            ))}
                          </select>
                          <button
                            type="button"
                            className="button-ghost shrink-0 px-3 py-1.5 text-[10px]"
                            disabled={busy || draft === team.plan}
                            onClick={() => void onSetPlan(team.id, draft)}
                          >
                            {busy ? (
                              <IconLoader size={12} className="animate-spin" />
                            ) : (
                              "Activar"
                            )}
                          </button>
                        </div>
                        <p className="mt-1.5 text-[9px] text-slate-400">
                          {team.members} plazas · {team.used} clips este mes
                        </p>
                      </div>
                    );
                  })}
                  {!adminTeams.length && (
                    <p className="rounded-xl border border-dashed border-slate-200 px-3 py-4 text-center text-[10px] text-slate-400">
                      Sin equipos todavía.
                    </p>
                  )}
                </div>
              </section>

              <form
                onSubmit={submitSuspend}
                className="space-y-2.5 rounded-2xl border border-rose-200 bg-rose-50/40 p-4"
              >
                <p className="inline-flex items-center gap-1.5 text-[12px] font-semibold text-rose-700">
                  <IconShield size={14} />
                  Suspender sesiones
                </p>
                <p className="text-[10px] leading-relaxed text-rose-600/80">
                  Cierra todas las sesiones activas de una cuenta. La cuenta y sus datos se
                  conservan.
                </p>
                <input
                  className="field"
                  type="email"
                  placeholder="correo@ejemplo.com"
                  value={suspendEmail}
                  onChange={(event) => setSuspendEmail(event.target.value)}
                  aria-label="Correo de la cuenta a suspender"
                />
                <button
                  type="submit"
                  className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-rose-600 px-4 py-2.5 text-[12px] font-semibold text-white transition hover:bg-rose-700 disabled:opacity-50"
                  disabled={busy || !suspendEmail.trim()}
                >
                  {busy ? <IconLoader size={14} className="animate-spin" /> : "Cerrar sesiones"}
                </button>
              </form>
            </>
          )}
        </div>
      </aside>
    </div>
  );
}
