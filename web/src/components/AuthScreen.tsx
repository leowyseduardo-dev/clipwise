import { useMemo, useState } from "react";
import type { FormEvent } from "react";

import { ApiError, sendJson } from "../lib/api";
import {
  IconAlert,
  IconArrowLeft,
  IconArrowRight,
  IconBolt,
  IconCheck,
  IconEye,
  IconEyeOff,
  IconFilm,
  IconLoader,
  IconLock,
  IconMail,
  IconScissors,
  IconShield,
  IconSparkles,
  IconUpload,
  IconUser,
  LogoMark,
} from "./icons";

type Mode = "login" | "register" | "forgot" | "reset";

type FormState = {
  name: string;
  email: string;
  password: string;
  confirm: string;
  terms: boolean;
};

const EMPTY: FormState = {
  name: "",
  email: "",
  password: "",
  confirm: "",
  terms: false,
};

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function resetToken(): string | null {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search).get("reset");
}

function strengthOf(password: string): number {
  if (!password) return 0;
  let score = 0;
  if (password.length >= 8) score += 1;
  if (password.length >= 12) score += 1;
  if (/[a-z]/.test(password) && /[A-Z]/.test(password)) score += 1;
  if (/\d/.test(password)) score += 1;
  if (/[^A-Za-z0-9]/.test(password)) score += 1;
  return Math.min(4, score);
}

const STRENGTH = [
  { label: "Muy débil", bar: "bg-rose-400", text: "text-rose-600" },
  { label: "Débil", bar: "bg-rose-400", text: "text-rose-600" },
  { label: "Aceptable", bar: "bg-amber-400", text: "text-amber-600" },
  { label: "Buena", bar: "bg-blue-500", text: "text-blue-600" },
  { label: "Excelente", bar: "bg-emerald-500", text: "text-emerald-600" },
];

function FieldError({ id, children }: { id: string; children?: string }) {
  if (!children) return null;
  return (
    <p id={id} className="mt-1.5 flex items-center gap-1.5 text-[11px] font-medium text-rose-600">
      <IconAlert size={12} />
      {children}
    </p>
  );
}

export function AuthScreen({
  onAuthenticated,
  initialMode = "login",
  onBack,
}: {
  onAuthenticated: () => Promise<void>;
  initialMode?: "login" | "register";
  onBack?: () => void;
}) {
  const [mode, setMode] = useState<Mode>(() => (resetToken() ? "reset" : initialMode));
  const [form, setForm] = useState<FormState>(EMPTY);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [capsLock, setCapsLock] = useState(false);
  const [sentTo, setSentTo] = useState("");

  const isRegister = mode === "register";
  const isReset = mode === "reset";
  const needsPassword = mode === "login" || isRegister || isReset;

  const emailValid = EMAIL_RE.test(form.email.trim());
  const nameValid = form.name.trim().length >= 2;
  const passwordValid = form.password.length >= 8;
  const confirmValid = form.confirm.length > 0 && form.confirm === form.password;
  const termsValid = form.terms;

  const strength = useMemo(() => strengthOf(form.password), [form.password]);
  const strengthMeta = STRENGTH[strength];

  const errors = {
    name: !nameValid ? "Escribe tu nombre (mínimo 2 caracteres)." : "",
    email: !emailValid ? "Introduce un correo electrónico válido." : "",
    password: !passwordValid ? "La contraseña debe tener al menos 8 caracteres." : "",
    confirm: !confirmValid
      ? form.confirm
        ? "Las contraseñas no coinciden."
        : "Confirma tu contraseña."
      : "",
    terms: !termsValid ? "Acepta los términos para continuar." : "",
  };

  function patch<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
    setError("");
  }

  function switchMode(next: Mode) {
    setMode(next);
    setError("");
    setNotice("");
    setTouched({});
    setShowPassword(false);
    setShowConfirm(false);
    if (next === "login") {
      setForm((current) => ({ ...current, password: "", confirm: "" }));
    }
    if (next === "register") {
      setForm((current) => ({ ...current, password: "", confirm: "" }));
    }
  }

  function markAllTouched() {
    setTouched({ name: true, email: true, password: true, confirm: true, terms: true });
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setNotice("");

    if (mode === "login") {
      setTouched({ email: true, password: true });
      if (!emailValid || form.password.length < 8) {
        setError("Revisa tu correo y tu contraseña (mínimo 8 caracteres).");
        return;
      }
    }

    if (isRegister) {
      markAllTouched();
      if (!nameValid || !emailValid || !passwordValid || !confirmValid || !termsValid) {
        setError("Revisa los campos marcados antes de crear tu cuenta.");
        return;
      }
    }

    if (mode === "forgot") {
      setTouched({ email: true });
      if (!emailValid) {
        setError("Introduce el correo de tu cuenta.");
        return;
      }
    }

    if (isReset) {
      setTouched({ password: true, confirm: true });
      if (!passwordValid || !confirmValid) {
        setError("Revisa la nueva contraseña.");
        return;
      }
    }

    setBusy(true);
    try {
      if (mode === "login") {
        await sendJson("/api/account/login", "POST", {
          email: form.email.trim(),
          password: form.password,
        });
        await onAuthenticated();
        return;
      }

      if (isRegister) {
        await sendJson("/api/account/register", "POST", {
          name: form.name.trim(),
          email: form.email.trim(),
          password: form.password,
          accept_terms: true,
        });
        await onAuthenticated();
        return;
      }

      if (mode === "forgot") {
        await sendJson("/api/account/forgot", "POST", { email: form.email.trim() });
        setSentTo(form.email.trim());
        setNotice(
          "Si ese correo tiene una cuenta, te enviamos un enlace para restablecer la contraseña. Revisa también la carpeta de spam.",
        );
        return;
      }

      const token = resetToken();
      if (!token) {
        setError("El enlace de recuperación no es válido. Solicita uno nuevo.");
        return;
      }
      await sendJson("/api/account/reset", "POST", {
        token,
        password: form.password,
      });
      window.history.replaceState({}, "", window.location.pathname);
      setForm(EMPTY);
      setMode("login");
      setNotice("Contraseña actualizada. Ya puedes iniciar sesión.");
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught.message);
      } else if (caught instanceof Error) {
        setError(caught.message);
      } else {
        setError("No pudimos completar la operación. Inténtalo de nuevo.");
      }
    } finally {
      setBusy(false);
    }
  }

  const heading =
    mode === "login"
      ? "Bienvenido de nuevo"
      : isRegister
        ? "Crea tu cuenta"
        : mode === "forgot"
          ? "Recupera tu acceso"
          : "Nueva contraseña";

  const subheading =
    mode === "login"
      ? "Entra a tu estudio y sigue convirtiendo videos largos en clips."
      : isRegister
        ? "Empieza gratis. Sin tarjeta. Tus primeros clips en minutos."
        : mode === "forgot"
          ? "Escribe el correo de tu cuenta y te enviaremos un enlace seguro."
          : "Elige una contraseña nueva para volver a tu estudio.";

  return (
    <main className="auth-canvas flex min-h-screen flex-col px-4 py-5 sm:px-6 sm:py-8">
      <div className="mx-auto flex w-full max-w-6xl items-center justify-between">
        <a href="/" className="flex items-center gap-3" aria-label="Clipwise">
          <LogoMark />
          <span className="font-display text-lg font-bold tracking-tight text-slate-900">
            Clipwise<span className="text-veru-ember">.</span>
          </span>
        </a>
        <a
          href="mailto:support@clipwise.app"
          className="hidden text-[11px] font-semibold text-slate-500 transition hover:text-slate-900 sm:block"
        >
          ¿Necesitas ayuda?
        </a>
      </div>

      <div className="mx-auto my-auto w-full max-w-6xl py-5 sm:py-8">
        <div className="auth-rise grid overflow-hidden rounded-[28px] border border-slate-200/90 bg-white shadow-[0_2px_4px_rgba(15,23,42,0.04),0_40px_100px_-50px_rgba(15,23,42,0.4)] min-[900px]:grid-cols-[1.02fr_0.98fr]">
          {/* Brand panel */}
          <section className="auth-brand relative hidden flex-col justify-between p-8 text-white min-[900px]:flex xl:p-10">
            <div className="relative z-10">
              <div className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-blue-50 backdrop-blur">
                <IconSparkles size={12} />
                Estudio de clips con IA
              </div>

              <h1 className="mt-6 max-w-[15ch] font-display text-[2.45rem] font-semibold leading-[1.03] tracking-[-0.045em] text-white xl:text-[2.8rem]">
                Del video largo al clip que frena el scroll.
              </h1>
              <p className="mt-4 max-w-[42ch] text-[13px] leading-relaxed text-blue-100/85">
                Sube tu archivo, deja que Clipwise encuentre los mejores momentos y
                recibe clips verticales con subtítulos, listos para publicar.
              </p>

              <div className="mt-6 space-y-2">
                <div className="auth-feature">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-white/15 text-white">
                    <IconUpload size={16} />
                  </span>
                  <div>
                    <p className="text-[13px] font-semibold text-white">Sube una vez</p>
                    <p className="mt-0.5 text-[11px] leading-relaxed text-blue-100/75">
                      Arrastra tu video y elige formato. Sin enlaces ni descargas.
                    </p>
                  </div>
                </div>
                <div className="auth-feature">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-white/15 text-white">
                    <IconScissors size={16} />
                  </span>
                  <div>
                    <p className="text-[13px] font-semibold text-white">La IA encuentra el gancho</p>
                    <p className="mt-0.5 text-[11px] leading-relaxed text-blue-100/75">
                      Whisper transcribe, puntúa los momentos y corta por ti.
                    </p>
                  </div>
                </div>
                <div className="auth-feature">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-white/15 text-white">
                    <IconBolt size={16} />
                  </span>
                  <div>
                    <p className="text-[13px] font-semibold text-white">Publica el mismo día</p>
                    <p className="mt-0.5 text-[11px] leading-relaxed text-blue-100/75">
                      Reencuadre, subtítulos y exportación en un solo flujo.
                    </p>
                  </div>
                </div>
              </div>
            </div>

            <div className="relative z-10 mt-7">
              <div className="rounded-2xl border border-white/15 bg-slate-950/25 p-3 backdrop-blur-sm">
                <div className="flex items-center justify-between text-[10px] font-semibold uppercase tracking-[0.16em] text-blue-100/70">
                  <span>Vista previa</span>
                  <span className="inline-flex items-center gap-1.5 text-emerald-300">
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-300" />
                    3 clips listos
                  </span>
                </div>
                <div className="mt-2.5 grid grid-cols-3 gap-2">
                  {[
                    { score: 94, time: "00:42", tone: "from-blue-400/30 to-blue-900/40" },
                    { score: 88, time: "01:07", tone: "from-sky-300/30 to-slate-900/40" },
                    { score: 81, time: "00:58", tone: "from-indigo-300/30 to-slate-900/40" },
                  ].map((clip, index) => (
                    <div
                      key={clip.time}
                      className={`relative overflow-hidden rounded-xl border border-white/15 bg-gradient-to-br ${clip.tone} p-2.5`}
                    >
                      <div className="flex h-14 items-end gap-1">
                        {[38, 62, 46, 78, 54, 88, 42, 68].map((height, bar) => (
                          <span
                            key={bar}
                            className="flex-1 rounded-full bg-white/25"
                            style={{ height: `${height}%` }}
                          />
                        ))}
                      </div>
                      <div className="mt-2 flex items-center justify-between text-[9px] font-semibold text-white/85">
                        <span>Clip {String(index + 1).padStart(2, "0")}</span>
                        <span className="rounded-full bg-white/15 px-1.5 py-0.5 text-emerald-200">
                          {clip.score}
                        </span>
                      </div>
                      <p className="mt-1 font-mono text-[9px] text-white/55">{clip.time}</p>
                    </div>
                  ))}
                </div>
              </div>

              <div className="mt-4 flex items-center gap-2 text-[10px] font-medium uppercase tracking-[0.14em] text-blue-100/55">
                <span>FFmpeg</span>
                <span className="h-1 w-1 rounded-full bg-blue-200/40" />
                <span>Whisper</span>
                <span className="h-1 w-1 rounded-full bg-blue-200/40" />
                <span>PySceneDetect</span>
              </div>
            </div>
          </section>

          {/* Form panel */}
          <section className="auth-rise-delayed flex flex-col justify-center px-6 py-8 sm:px-10 sm:py-10 xl:px-12">
            <div className="mx-auto w-full max-w-[25rem]">
              {onBack && (
                <button
                  type="button"
                  onClick={onBack}
                  className="mb-5 inline-flex items-center gap-1.5 text-[11px] font-semibold text-slate-500 transition hover:text-slate-900"
                >
                  <IconArrowLeft size={13} />
                  Volver a la página principal
                </button>
              )}

              {mode === "login" || isRegister ? (
                <div className="auth-seg mb-7" role="tablist" aria-label="Acceso">
                  <button
                    type="button"
                    role="tab"
                    aria-selected={mode === "login"}
                    onClick={() => switchMode("login")}
                    className={`auth-seg-btn ${
                      mode === "login" ? "auth-seg-btn-active" : "auth-seg-btn-idle"
                    }`}
                  >
                    Iniciar sesión
                  </button>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={isRegister}
                    onClick={() => switchMode("register")}
                    className={`auth-seg-btn ${
                      isRegister ? "auth-seg-btn-active" : "auth-seg-btn-idle"
                    }`}
                  >
                    Crear cuenta
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => switchMode("login")}
                  className="mb-6 inline-flex items-center gap-1.5 text-[11px] font-semibold text-slate-500 transition hover:text-slate-900"
                >
                  <IconArrowLeft size={13} />
                  Volver a iniciar sesión
                </button>
              )}

              <h2 className="font-display text-[1.65rem] font-semibold tracking-[-0.03em] text-slate-900">
                {heading}
              </h2>
              <p className="mt-1.5 text-[13px] leading-relaxed text-slate-500">{subheading}</p>

              {error && (
                <div
                  role="alert"
                  aria-live="assertive"
                  className="mt-5 flex items-start gap-2.5 rounded-xl border border-rose-200 bg-rose-50 px-3.5 py-3 text-[12px] font-medium leading-relaxed text-rose-700"
                >
                  <IconAlert size={15} className="mt-0.5 shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              {notice && (
                <div
                  role="status"
                  aria-live="polite"
                  className="mt-5 flex items-start gap-2.5 rounded-xl border border-emerald-200 bg-emerald-50 px-3.5 py-3 text-[12px] font-medium leading-relaxed text-emerald-700"
                >
                  <IconCheck size={15} className="mt-0.5 shrink-0" />
                  <span>{notice}</span>
                </div>
              )}

              <form className="mt-6 space-y-4" onSubmit={submit} noValidate>
                {isRegister && (
                  <div>
                    <label className="auth-label" htmlFor="auth-name">
                      Nombre
                    </label>
                    <div className="relative">
                      <IconUser size={17} className="auth-icon" />
                      <input
                        id="auth-name"
                        name="name"
                        type="text"
                        autoComplete="name"
                        maxLength={80}
                        placeholder="Tu nombre"
                        className="auth-input"
                        value={form.name}
                        onChange={(event) => patch("name", event.target.value)}
                        onBlur={() => setTouched((current) => ({ ...current, name: true }))}
                        aria-invalid={touched.name && !nameValid}
                        aria-describedby={touched.name && !nameValid ? "err-name" : undefined}
                        autoFocus={isRegister}
                      />
                    </div>
                    <FieldError id="err-name">{touched.name ? errors.name : ""}</FieldError>
                  </div>
                )}

                {mode !== "reset" && (
                  <div>
                    <label className="auth-label" htmlFor="auth-email">
                      Correo electrónico
                    </label>
                    <div className="relative">
                      <IconMail size={17} className="auth-icon" />
                      <input
                        id="auth-email"
                        name="email"
                        type="email"
                        inputMode="email"
                        autoComplete="email"
                        maxLength={254}
                        placeholder="tu@correo.com"
                        className="auth-input"
                        value={form.email}
                        onChange={(event) => patch("email", event.target.value)}
                        onBlur={() => setTouched((current) => ({ ...current, email: true }))}
                        aria-invalid={touched.email && !emailValid}
                        aria-describedby={touched.email && !emailValid ? "err-email" : undefined}
                        autoFocus={mode === "login" || mode === "forgot"}
                      />
                    </div>
                    <FieldError id="err-email">{touched.email ? errors.email : ""}</FieldError>
                  </div>
                )}

                {needsPassword && (
                  <div>
                    <div className="auth-label">
                      <label htmlFor="auth-password">
                        {isReset ? "Nueva contraseña" : "Contraseña"}
                      </label>
                      {mode === "login" && (
                        <button
                          type="button"
                          className="auth-link text-[11px]"
                          onClick={() => switchMode("forgot")}
                        >
                          ¿La olvidaste?
                        </button>
                      )}
                    </div>
                    <div className="relative">
                      <IconLock size={17} className="auth-icon" />
                      <input
                        id="auth-password"
                        name="password"
                        type={showPassword ? "text" : "password"}
                        autoComplete={isRegister || isReset ? "new-password" : "current-password"}
                        maxLength={256}
                        placeholder={isRegister || isReset ? "Mínimo 8 caracteres" : "Tu contraseña"}
                        className="auth-input"
                        value={form.password}
                        onChange={(event) => patch("password", event.target.value)}
                        onBlur={() => setTouched((current) => ({ ...current, password: true }))}
                        onKeyUp={(event) =>
                          setCapsLock(event.getModifierState?.("CapsLock") ?? false)
                        }
                        aria-invalid={touched.password && !passwordValid}
                        aria-describedby={
                          touched.password && !passwordValid ? "err-password" : undefined
                        }
                        autoFocus={isReset}
                      />
                      <button
                        type="button"
                        className="auth-eye"
                        onClick={() => setShowPassword((value) => !value)}
                        aria-label={showPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
                        title={showPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
                      >
                        {showPassword ? <IconEyeOff size={17} /> : <IconEye size={17} />}
                      </button>
                    </div>

                    {capsLock && (
                      <p className="mt-1.5 flex items-center gap-1.5 text-[11px] font-medium text-amber-600">
                        <IconAlert size={12} />
                        Bloq Mayús está activado.
                      </p>
                    )}

                    {(isRegister || isReset) && (
                      <div className="mt-2.5">
                        <div className="flex gap-1.5">
                          {[0, 1, 2, 3].map((index) => (
                            <span
                              key={index}
                              className={`auth-strength ${
                                form.password && index < strength ? strengthMeta.bar : ""
                              }`}
                            />
                          ))}
                        </div>
                        <p className="mt-1.5 text-[10px] font-medium text-slate-400">
                          {form.password ? (
                            <span className={strengthMeta.text}>
                              Seguridad: {strengthMeta.label}
                            </span>
                          ) : (
                            "Usa 8 caracteres o más. Mezcla mayúsculas, números y símbolos."
                          )}
                        </p>
                      </div>
                    )}

                    <FieldError id="err-password">
                      {touched.password ? errors.password : ""}
                    </FieldError>
                  </div>
                )}

                {(isRegister || isReset) && (
                  <div>
                    <label className="auth-label" htmlFor="auth-confirm">
                      Confirmar contraseña
                    </label>
                    <div className="relative">
                      <IconShield size={17} className="auth-icon" />
                      <input
                        id="auth-confirm"
                        name="confirm"
                        type={showConfirm ? "text" : "password"}
                        autoComplete="new-password"
                        maxLength={256}
                        placeholder="Repite la contraseña"
                        className="auth-input"
                        value={form.confirm}
                        onChange={(event) => patch("confirm", event.target.value)}
                        onBlur={() => setTouched((current) => ({ ...current, confirm: true }))}
                        aria-invalid={touched.confirm && !confirmValid}
                        aria-describedby={
                          touched.confirm && !confirmValid ? "err-confirm" : undefined
                        }
                      />
                      <button
                        type="button"
                        className="auth-eye"
                        onClick={() => setShowConfirm((value) => !value)}
                        aria-label={showConfirm ? "Ocultar contraseña" : "Mostrar contraseña"}
                        title={showConfirm ? "Ocultar contraseña" : "Mostrar contraseña"}
                      >
                        {showConfirm ? <IconEyeOff size={17} /> : <IconEye size={17} />}
                      </button>
                    </div>
                    <FieldError id="err-confirm">
                      {touched.confirm ? errors.confirm : ""}
                    </FieldError>
                  </div>
                )}

                {isRegister && (
                  <div>
                    <label className="flex cursor-pointer items-start gap-2.5 text-[11px] leading-relaxed text-slate-500">
                      <input
                        type="checkbox"
                        className="auth-check"
                        checked={form.terms}
                        onChange={(event) => patch("terms", event.target.checked)}
                        aria-invalid={touched.terms && !termsValid}
                        aria-describedby={touched.terms && !termsValid ? "err-terms" : undefined}
                      />
                      <span>
                        Acepto los{" "}
                        <a
                          href="/terminos.html"
                          target="_blank"
                          rel="noreferrer"
                          className="auth-link"
                        >
                          términos y condiciones
                        </a>{" "}
                        y la{" "}
                        <a
                          href="/privacidad.html"
                          target="_blank"
                          rel="noreferrer"
                          className="auth-link"
                        >
                          política de privacidad
                        </a>
                        .
                      </span>
                    </label>
                    <FieldError id="err-terms">{touched.terms ? errors.terms : ""}</FieldError>
                  </div>
                )}

                <button type="submit" className="button-primary w-full py-3" disabled={busy}>
                  {busy ? (
                    <>
                      <IconLoader size={16} className="animate-spin" />
                      {isRegister
                        ? "Creando tu cuenta…"
                        : mode === "login"
                          ? "Entrando…"
                          : mode === "forgot"
                            ? "Enviando…"
                            : "Guardando…"}
                    </>
                  ) : (
                    <>
                      {mode === "login"
                        ? "Entrar a Clipwise"
                        : isRegister
                          ? "Crear mi cuenta gratis"
                          : mode === "forgot"
                            ? "Enviar enlace de recuperación"
                            : "Guardar contraseña"}
                      <IconArrowRight size={16} />
                    </>
                  )}
                </button>
              </form>

              {mode === "login" && (
                <p className="mt-5 text-center text-[12px] text-slate-500">
                  ¿Aún no tienes cuenta?{" "}
                  <button
                    type="button"
                    className="auth-link"
                    onClick={() => switchMode("register")}
                  >
                    Crea una gratis
                  </button>
                </p>
              )}

              {isRegister && (
                <p className="mt-5 text-center text-[12px] text-slate-500">
                  ¿Ya tienes cuenta?{" "}
                  <button type="button" className="auth-link" onClick={() => switchMode("login")}>
                    Inicia sesión
                  </button>
                </p>
              )}

              {mode === "forgot" && sentTo && (
                <button
                  type="button"
                  className="mt-5 inline-flex w-full items-center justify-center gap-1.5 text-[12px] font-semibold text-slate-500 transition hover:text-slate-900"
                  onClick={() => switchMode("login")}
                >
                  <IconArrowLeft size={13} />
                  Volver a iniciar sesión
                </button>
              )}

              <div className="mt-8 flex items-center justify-between border-t border-slate-100 pt-5 text-[10px] text-slate-400">
                <span>© 2026 Clipwise</span>
                <span className="inline-flex items-center gap-1.5">
                  <IconShield size={11} />
                  Sesión cifrada y protegida
                </span>
              </div>
            </div>
          </section>
        </div>

        <p className="mt-5 flex items-center justify-center gap-2 text-center text-[10px] text-slate-400">
          <IconFilm size={12} />
          Procesamiento con FFmpeg y Whisper. Tus videos permanecen en tu espacio de trabajo.
        </p>
      </div>
    </main>
  );
}
