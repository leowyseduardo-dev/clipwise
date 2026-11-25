import {
  IconArrowRight,
  IconBolt,
  IconCheck,
  IconChevronDown,
  IconClock,
  IconDownload,
  IconFilm,
  IconLink,
  IconPlay,
  IconScissors,
  IconShield,
  IconSparkles,
  IconUpload,
  IconYouTube,
  LogoMark,
} from "./icons";

type AuthMode = "login" | "register";

const NAV = [
  { label: "Producto", href: "#producto" },
  { label: "Cómo funciona", href: "#como-funciona" },
  { label: "Planes", href: "#planes" },
  { label: "Preguntas", href: "#faq" },
];

const PLATFORMS = [
  { label: "YouTube", detail: "Vídeos y directos" },
  { label: "Kick", detail: "Streams completos" },
  { label: "Twitch", detail: "VODs y clips" },
  { label: "MP4 · MOV", detail: "Archivo local" },
];

const FEATURES = [
  {
    icon: IconLink,
    title: "Pega el enlace y listo",
    copy: "YouTube, Kick o Twitch. Clipwise descarga el vídeo, lo analiza y corta los mejores momentos sin que toques un editor.",
  },
  {
    icon: IconSparkles,
    title: "La IA encuentra el gancho",
    copy: "Whisper transcribe con marcas de tiempo y un modelo de puntuación elige los momentos con más retención, risas o tensión.",
  },
  {
    icon: IconScissors,
    title: "Reencuadre 9:16 automático",
    copy: "Seguimiento de cara y de zona activa para que el clip llene la pantalla vertical sin recortar lo importante.",
  },
  {
    icon: IconFilm,
    title: "9 estilos de subtítulos",
    copy: "Shorts, impacto, neón, píldora, caja y más. Palabra a palabra, con tiempos ajustados y contraste legible.",
  },
  {
    icon: IconBolt,
    title: "Editor de clips incluido",
    copy: "Cambia el gancho, el rótulo, las cámaras o los subtítulos y vuelve a renderizar solo ese clip en segundos.",
  },
  {
    icon: IconClock,
    title: "Calendario de publicación",
    copy: "Organiza la semana, marca qué clip sale cada día y descarga todo el paquete en un solo ZIP.",
  },
];

const STEPS = [
  {
    number: "01",
    title: "Pega un enlace",
    copy: "Copia la URL del vídeo o del directo. También puedes subir un archivo si ya lo tienes en el disco.",
  },
  {
    number: "02",
    title: "Clipwise lo trabaja",
    copy: "Descarga, transcribe, detecta escenas y puntúa los momentos. Tú solo esperas el resultado.",
  },
  {
    number: "03",
    title: "Revisa y publica",
    copy: "Ajusta lo que quieras, elige el día y descarga los clips verticales listos para TikTok, Reels o Shorts.",
  },
];

const INCLUDED = [
  "Transcripción con Whisper",
  "Detección de escenas",
  "Reencuadre vertical",
  "Subtítulos animados",
  "Editor por clip",
  "Exportación H.264 + AAC",
];

const PLANS = [
  {
    name: "Starter",
    price: 0,
    tagline: "Para probar el flujo completo",
    features: [
      "2 clips al día",
      "20 clips al mes",
      "1 proyecto a la vez",
      "1080p sin marca de agua forzada",
      "Todos los estilos de subtítulos",
    ],
    cta: "Empezar gratis",
    highlight: false,
    note: "Sin tarjeta",
  },
  {
    name: "Creator",
    price: 5,
    tagline: "Para publicar cada semana",
    features: [
      "120 clips al mes",
      "1080p sin marca de agua forzada",
      "3 proyectos a la vez",
      "2 plazas de equipo",
      "Calendario y editor completos",
    ],
    cta: "Elegir Creator",
    highlight: true,
    note: "Mejor valor",
  },
  {
    name: "Studio",
    price: 10,
    tagline: "Para producir a escala",
    features: [
      "400 clips al mes",
      "8 proyectos a la vez",
      "5 plazas de equipo",
      "Todo lo de Creator, sin límites de estilo",
      "1080p sin marca de agua forzada",
    ],
    cta: "Elegir Studio",
    highlight: false,
    note: "Para equipos y agencias",
  },
];

const FAQ = [
  {
    q: "¿Qué enlaces puedo usar?",
    a: "YouTube (vídeos y directos), Kick y Twitch. Pega la URL pública del vídeo o del VOD. Si el contenido es privado o requiere inicio de sesión, descárgalo y súbelo como archivo.",
  },
  {
    q: "¿Cuánto tarda en salir un clip?",
    a: "Un vídeo de 10 minutos suele tardar entre 2 y 4 minutos. Un directo de 3 horas puede tardar bastante más: la descarga y la transcripción son el cuello de botella. Verás el progreso en tiempo real.",
  },
  {
    q: "¿Puedo editar lo que genera la IA?",
    a: "Sí. Cada clip tiene su propio editor: cambia el gancho, el rótulo, la plantilla de cámaras, el estilo de subtítulos o el texto y vuelve a renderizar solo ese clip.",
  },
  {
    q: "¿Los clips llevan marca de agua?",
    a: "No. Todos los planes exportan en 1080p sin marca de agua forzada, listo para subir a TikTok, Reels o Shorts. Los planes pagados añaden más clips, proyectos simultáneos y plazas de equipo.",
  },
  {
    q: "¿Puedo cambiar o cancelar mi plan?",
    a: "Sí. Desde Mi cuenta → Plan puedes cancelar la suscripción; mantienes el acceso hasta el final del periodo pagado. Para cambiar de plan, suscríbete al nuevo y cancelaremos el anterior automáticamente.",
  },
  {
    q: "¿Qué pasa con mis vídeos?",
    a: "Cada equipo tiene su propio espacio de trabajo aislado. Los archivos se usan para procesar tus clips y se pueden borrar desde la biblioteca cuando termines.",
  },
];

export function MarketingPage({ onStart }: { onStart: (mode: AuthMode) => void }) {
  return (
    <div className="relative z-10 min-h-screen bg-white">
      <header className="sticky top-0 z-40 border-b border-slate-200/80 bg-white/85 backdrop-blur-xl">
        <div className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
          <a href="#top" className="flex items-center gap-2.5" aria-label="Clipwise">
            <LogoMark />
            <span className="font-display text-lg font-bold tracking-tight text-slate-900">
              Clipwise<span className="text-veru-ember">.</span>
            </span>
          </a>

          <nav className="hidden items-center gap-1 md:flex" aria-label="Principal">
            {NAV.map((item) => (
              <a
                key={item.href}
                href={item.href}
                className="rounded-lg px-3 py-2 text-[12px] font-semibold text-slate-600 transition hover:bg-slate-100 hover:text-slate-900"
              >
                {item.label}
              </a>
            ))}
          </nav>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => onStart("login")}
              className="hidden rounded-xl px-3.5 py-2 text-[12px] font-semibold text-slate-600 transition hover:bg-slate-100 hover:text-slate-900 sm:inline-flex"
            >
              Iniciar sesión
            </button>
            <button
              type="button"
              onClick={() => onStart("register")}
              className="button-primary px-4 py-2 text-[12px]"
            >
              Empezar gratis
              <IconArrowRight size={14} />
            </button>
          </div>
        </div>
      </header>

      <main id="top">
        {/* Hero */}
        <section className="relative overflow-hidden">
          <div className="pointer-events-none absolute inset-0">
            <div className="absolute -top-40 left-1/2 h-[520px] w-[820px] -translate-x-1/2 rounded-full bg-blue-200/40 blur-3xl" />
            <div className="absolute right-0 top-40 h-72 w-72 rounded-full bg-sky-100 blur-3xl" />
          </div>

          <div className="relative mx-auto grid w-full max-w-6xl gap-12 px-4 pb-20 pt-14 sm:px-6 lg:grid-cols-[1.02fr_0.98fr] lg:items-center lg:pb-24 lg:pt-20">
            <div className="auth-rise">
              <span className="inline-flex items-center gap-2 rounded-full border border-blue-200 bg-blue-50 px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.16em] text-blue-700">
                <IconSparkles size={12} />
                Clips desde un enlace
              </span>

              <h1 className="mt-5 max-w-[16ch] font-display text-[2.6rem] font-semibold leading-[1.02] tracking-[-0.05em] text-slate-900 sm:text-[3.4rem] lg:text-[3.6rem]">
                Pega un enlace.
                <br />
                Recibe clips que{" "}
                <span className="accent-italic">frenan el scroll.</span>
              </h1>

              <p className="mt-5 max-w-[52ch] text-[15px] leading-relaxed text-slate-500">
                Clipwise descarga tu vídeo de YouTube, Kick o Twitch, encuentra los
                mejores momentos y te devuelve clips verticales con subtítulos,
                reencuadre automático y listos para publicar.
              </p>

              <div className="mt-7 flex flex-col gap-3 sm:flex-row">
                <button
                  type="button"
                  onClick={() => onStart("register")}
                  className="button-primary px-6 py-3 text-[14px]"
                >
                  Crear mi cuenta gratis
                  <IconArrowRight size={16} />
                </button>
                <a
                  href="#como-funciona"
                  className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-5 py-3 text-[13px] font-semibold text-slate-700 transition hover:border-slate-300 hover:bg-slate-50"
                >
                  <IconPlay size={15} />
                  Ver cómo funciona
                </a>
              </div>

              <div className="mt-6 flex flex-wrap items-center gap-x-5 gap-y-2 text-[11px] font-medium text-slate-400">
                <span className="inline-flex items-center gap-1.5">
                  <IconCheck size={13} className="text-emerald-500" />
                  Sin tarjeta para empezar
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <IconCheck size={13} className="text-emerald-500" />
                  2 clips gratis al día
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <IconShield size={13} className="text-emerald-500" />
                  Tu espacio, aislado
                </span>
              </div>
            </div>

            <div className="relative auth-rise-delayed">
              <div className="absolute -inset-6 rounded-[36px] bg-gradient-to-tr from-blue-100/70 via-transparent to-sky-100/60 blur-2xl" />

              <div className="relative rounded-[28px] border border-slate-200 bg-white p-4 shadow-[0_2px_4px_rgba(15,23,42,0.04),0_40px_100px_-50px_rgba(15,23,42,0.45)] sm:p-5">
                <div className="flex items-center justify-between">
                  <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-slate-400">
                    Nuevo trabajo
                  </p>
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[9px] font-bold uppercase tracking-[0.08em] text-emerald-700">
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                    Motor listo
                  </span>
                </div>

                <div className="mt-3 rounded-2xl border border-slate-200 bg-slate-50/70 p-3">
                  <div className="flex items-center gap-2 rounded-xl border border-blue-200 bg-white px-3 py-2.5 shadow-[0_0_0_3px_rgba(37,99,235,0.06)]">
                    <IconLink size={15} className="shrink-0 text-blue-600" />
                    <span className="min-w-0 flex-1 truncate font-mono text-[10px] text-slate-500">
                      youtube.com/watch?v=dQw4w9WgXcQ
                    </span>
                    <span className="rounded-md bg-blue-600 px-2 py-1 text-[9px] font-bold text-white">
                      Pegar
                    </span>
                  </div>

                  <div className="mt-2.5 flex flex-wrap gap-1.5">
                    {["YouTube", "Kick", "Twitch"].map((platform, index) => (
                      <span
                        key={platform}
                        className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[9px] font-semibold ${
                          index === 0
                            ? "border-blue-200 bg-blue-50 text-blue-700"
                            : "border-slate-200 bg-white text-slate-500"
                        }`}
                      >
                        {index === 0 && <IconYouTube size={11} />}
                        {platform}
                      </span>
                    ))}
                    <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[9px] font-semibold text-slate-500">
                      <IconUpload size={11} />
                      Archivo
                    </span>
                  </div>

                  <div className="mt-3 flex items-center justify-between gap-3">
                    <span className="inline-flex items-center gap-1.5 text-[9px] font-medium text-slate-400">
                      <IconClock size={11} />
                      ~3 min para un vídeo de 10 min
                    </span>
                    <span className="rounded-lg bg-blue-600 px-3 py-1.5 text-[10px] font-bold text-white shadow-[0_8px_18px_-10px_rgba(37,99,235,0.9)]">
                      Generar clips
                    </span>
                  </div>
                </div>

                <div className="mt-3 grid grid-cols-3 gap-2">
                  {[
                    { score: 94, time: "00:42", tone: "from-blue-500 to-blue-900" },
                    { score: 88, time: "01:07", tone: "from-sky-400 to-slate-900" },
                    { score: 81, time: "00:58", tone: "from-indigo-400 to-slate-900" },
                  ].map((clip, index) => (
                    <div
                      key={clip.time}
                      className={`relative overflow-hidden rounded-xl bg-gradient-to-br ${clip.tone} p-2`}
                    >
                      <div className="flex h-24 items-end gap-1">
                        {[38, 62, 46, 78, 54, 88, 42, 68].map((height, bar) => (
                          <span
                            key={bar}
                            className="flex-1 rounded-full bg-white/25"
                            style={{ height: `${height}%` }}
                          />
                        ))}
                      </div>
                      <div className="absolute left-1.5 top-1.5 rounded-md bg-black/35 px-1.5 py-0.5 text-[8px] font-bold text-white backdrop-blur">
                        {clip.score}
                      </div>
                      <p className="mt-2 text-[8px] font-bold uppercase tracking-[0.1em] text-white/80">
                        Clip {String(index + 1).padStart(2, "0")}
                      </p>
                      <p className="font-mono text-[8px] text-white/60">{clip.time}</p>
                    </div>
                  ))}
                </div>

                <div className="mt-3 flex items-center justify-between rounded-xl border border-slate-200 bg-white px-3 py-2">
                  <span className="inline-flex items-center gap-1.5 text-[9px] font-semibold text-slate-500">
                    <IconDownload size={11} />
                    3 clips · 9:16 · subtítulos incluidos
                  </span>
                  <span className="text-[9px] font-bold text-blue-600">Descargar ZIP</span>
                </div>
              </div>

              <div className="absolute -bottom-5 -left-4 hidden items-center gap-2 rounded-2xl border border-slate-200 bg-white px-3 py-2 shadow-panel sm:flex">
                <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-blue-50 text-blue-600">
                  <IconScissors size={14} />
                </span>
                <div>
                  <p className="text-[10px] font-bold text-slate-800">Reencuadre automático</p>
                  <p className="text-[9px] text-slate-400">Seguimiento de cara y juego</p>
                </div>
              </div>
            </div>
          </div>

          <div className="relative mx-auto w-full max-w-6xl px-4 pb-14 sm:px-6">
            <div className="rounded-2xl border border-slate-200 bg-slate-50/70 px-4 py-4">
              <p className="text-center text-[9px] font-bold uppercase tracking-[0.22em] text-slate-400">
                Funciona con los enlaces que ya usas
              </p>
              <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
                {PLATFORMS.map((platform) => (
                  <div
                    key={platform.label}
                    className="flex items-center gap-2.5 rounded-xl border border-slate-200 bg-white px-3 py-2.5"
                  >
                    <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-slate-100 text-slate-500">
                      {platform.label === "YouTube" ? (
                        <IconYouTube size={14} />
                      ) : (
                        <IconFilm size={14} />
                      )}
                    </span>
                    <div className="min-w-0">
                      <p className="truncate text-[11px] font-bold text-slate-700">
                        {platform.label}
                      </p>
                      <p className="truncate text-[9px] text-slate-400">{platform.detail}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* Features */}
        <section id="producto" className="scroll-mt-24 border-t border-slate-100 py-20">
          <div className="mx-auto w-full max-w-6xl px-4 sm:px-6">
            <div className="max-w-2xl">
              <p className="eyebrow">El producto</p>
              <h2 className="mt-3 font-display text-[2rem] font-semibold leading-[1.08] tracking-[-0.04em] text-slate-900 sm:text-[2.5rem]">
                Un estudio entero detrás de una caja de texto.
              </h2>
              <p className="mt-4 text-[14px] leading-relaxed text-slate-500">
                No necesitas descargar nada, ni aprender un editor, ni montar un
                pipeline. Pega la URL y Clipwise hace el trabajo pesado.
              </p>
            </div>

            <div className="mt-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {FEATURES.map((feature) => {
                const Icon = feature.icon;
                return (
                  <article
                    key={feature.title}
                    className="group rounded-2xl border border-slate-200 bg-white p-5 transition hover:-translate-y-0.5 hover:border-blue-200 hover:shadow-panel"
                  >
                    <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-50 text-blue-600 transition group-hover:bg-blue-600 group-hover:text-white">
                      <Icon size={18} />
                    </span>
                    <h3 className="mt-4 font-display text-[15px] font-semibold tracking-tight text-slate-900">
                      {feature.title}
                    </h3>
                    <p className="mt-1.5 text-[12px] leading-relaxed text-slate-500">
                      {feature.copy}
                    </p>
                  </article>
                );
              })}
            </div>
          </div>
        </section>

        {/* How it works */}
        <section id="como-funciona" className="scroll-mt-24 border-t border-slate-100 bg-slate-50/60 py-20">
          <div className="mx-auto w-full max-w-6xl px-4 sm:px-6">
            <div className="flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
              <div className="max-w-xl">
                <p className="eyebrow">Cómo funciona</p>
                <h2 className="mt-3 font-display text-[2rem] font-semibold leading-[1.08] tracking-[-0.04em] text-slate-900 sm:text-[2.5rem]">
                  Tres pasos. Cero timeline.
                </h2>
              </div>
              <p className="max-w-sm text-[12px] leading-relaxed text-slate-500">
                El mismo flujo sirve para un vídeo de 10 minutos que para un directo
                de 6 horas. La diferencia es el tiempo de espera, no el resultado.
              </p>
            </div>

            <div className="mt-10 grid gap-3 md:grid-cols-3">
              {STEPS.map((step, index) => (
                <div key={step.number} className="relative rounded-2xl border border-slate-200 bg-white p-5">
                  <div className="flex items-center justify-between">
                    <span className="font-display text-[2rem] font-semibold tracking-tighter text-blue-100">
                      {step.number}
                    </span>
                    {index < STEPS.length - 1 && (
                      <IconArrowRight size={16} className="hidden text-slate-300 md:block" />
                    )}
                  </div>
                  <h3 className="mt-2 font-display text-[16px] font-semibold tracking-tight text-slate-900">
                    {step.title}
                  </h3>
                  <p className="mt-1.5 text-[12px] leading-relaxed text-slate-500">{step.copy}</p>
                </div>
              ))}
            </div>

            <div className="mt-8 rounded-2xl border border-blue-200 bg-blue-50/60 p-5">
              <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-blue-700">
                Incluido en todos los planes
              </p>
              <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {INCLUDED.map((item) => (
                  <span key={item} className="inline-flex items-center gap-2 text-[12px] font-medium text-slate-700">
                    <IconCheck size={14} className="shrink-0 text-blue-600" />
                    {item}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* Pricing */}
        <section id="planes" className="scroll-mt-24 py-20">
          <div className="mx-auto w-full max-w-6xl px-4 sm:px-6">
            <div className="mx-auto max-w-2xl text-center">
              <p className="eyebrow">Planes</p>
              <h2 className="mt-3 font-display text-[2rem] font-semibold leading-[1.08] tracking-[-0.04em] text-slate-900 sm:text-[2.5rem]">
                Precios de verdad, sin letra pequeña.
              </h2>
              <p className="mt-4 text-[14px] leading-relaxed text-slate-500">
                Empieza gratis. Cuando el flujo te convenza, sube a Creator por 5 $ al
                mes o a Studio por 10 $. Sin contratos ni permanencia.
              </p>
            </div>

            <div className="mt-10 grid gap-4 lg:grid-cols-3 lg:items-start">
              {PLANS.map((plan) => (
                <article
                  key={plan.name}
                  className={`relative flex h-full flex-col rounded-[24px] border p-6 ${
                    plan.highlight
                      ? "border-blue-300 bg-white shadow-[0_2px_4px_rgba(15,23,42,0.04),0_30px_70px_-40px_rgba(37,99,235,0.55)] lg:-mt-3 lg:pb-8"
                      : "border-slate-200 bg-white"
                  }`}
                >
                  {plan.highlight && (
                    <span className="mb-4 inline-flex items-center self-center rounded-full bg-blue-600 px-3 py-1 text-[9px] font-bold uppercase tracking-[0.14em] text-white shadow-[0_8px_18px_-10px_rgba(37,99,235,0.9)] lg:absolute lg:-top-3 lg:left-1/2 lg:mb-0 lg:-translate-x-1/2">
                      Más recomendado
                    </span>
                  )}

                  <div className="flex items-baseline justify-between gap-3">
                    <h3 className="font-display text-[17px] font-semibold tracking-tight text-slate-900">
                      {plan.name}
                    </h3>
                    <span
                      className={`rounded-full px-2.5 py-1 text-[9px] font-bold uppercase tracking-[0.08em] ${
                        plan.highlight
                          ? "bg-blue-50 text-blue-700"
                          : "bg-slate-100 text-slate-500"
                      }`}
                    >
                      {plan.note}
                    </span>
                  </div>
                  <p className="mt-1 text-[11px] text-slate-400">{plan.tagline}</p>

                  <div className="mt-5 flex items-end gap-1.5">
                    <span className="font-display text-[2.6rem] font-semibold leading-none tracking-[-0.05em] text-slate-900">
                      ${plan.price}
                    </span>
                    <span className="pb-1 text-[11px] font-medium text-slate-400">
                      {plan.price === 0 ? "para siempre" : "al mes"}
                    </span>
                  </div>

                  <ul className="mt-5 flex-1 space-y-2.5 border-t border-slate-100 pt-5">
                    {plan.features.map((feature) => (
                      <li key={feature} className="flex items-start gap-2 text-[12px] text-slate-600">
                        <IconCheck size={14} className="mt-0.5 shrink-0 text-blue-600" />
                        {feature}
                      </li>
                    ))}
                  </ul>

                  <button
                    type="button"
                    onClick={() => onStart("register")}
                    className={`mt-6 w-full ${
                      plan.highlight ? "button-primary py-3" : "button-ghost py-3"
                    }`}
                  >
                    {plan.cta}
                    <IconArrowRight size={14} />
                  </button>
                  {plan.price > 0 && (
                    <p className="mt-2 text-center text-[9px] text-slate-400">
                      Suscripción automática con PayPal desde tu cuenta
                    </p>
                  )}
                </article>
              ))}
            </div>

            <p className="mt-6 text-center text-[11px] text-slate-400">
              Precios en USD. El plan Starter no pide tarjeta. Los planes Creator y
              Studio se pagan con PayPal y se activan automáticamente al confirmar la
              suscripción.
            </p>
          </div>
        </section>

        {/* FAQ */}
        <section id="faq" className="scroll-mt-24 border-t border-slate-100 bg-slate-50/60 py-20">
          <div className="mx-auto grid w-full max-w-6xl gap-10 px-4 sm:px-6 lg:grid-cols-[0.8fr_1.2fr]">
            <div>
              <p className="eyebrow">Preguntas</p>
              <h2 className="mt-3 font-display text-[2rem] font-semibold leading-[1.08] tracking-[-0.04em] text-slate-900">
                Lo que suele preguntar la gente.
              </h2>
              <p className="mt-4 max-w-sm text-[13px] leading-relaxed text-slate-500">
                ¿Te falta algo? Escríbenos a{" "}
                <a
                  href="mailto:support@clipwise.app"
                  className="font-semibold text-blue-600 hover:underline"
                >
                  support@clipwise.app
                </a>{" "}
                y te contesta una persona.
              </p>
            </div>

            <div className="space-y-2">
              {FAQ.map((item) => (
                <details
                  key={item.q}
                  className="group rounded-2xl border border-slate-200 bg-white px-4 py-3.5 open:border-blue-200"
                >
                  <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-[13px] font-semibold text-slate-800 [&::-webkit-details-marker]:hidden">
                    {item.q}
                    <IconChevronDown
                      size={15}
                      className="shrink-0 text-slate-400 transition group-open:rotate-180"
                    />
                  </summary>
                  <p className="mt-2.5 text-[12px] leading-relaxed text-slate-500">{item.a}</p>
                </details>
              ))}
            </div>
          </div>
        </section>

        {/* Final CTA */}
        <section className="py-20">
          <div className="mx-auto w-full max-w-6xl px-4 sm:px-6">
            <div className="relative overflow-hidden rounded-[28px] bg-gradient-to-br from-blue-700 via-blue-600 to-blue-800 px-6 py-12 text-center text-white sm:px-10">
              <div className="pointer-events-none absolute -left-16 -top-20 h-64 w-64 rounded-full bg-white/10 blur-2xl" />
              <div className="pointer-events-none absolute -bottom-24 right-0 h-72 w-72 rounded-full bg-sky-300/20 blur-3xl" />
              <div className="relative mx-auto max-w-2xl">
                <p className="text-[10px] font-bold uppercase tracking-[0.22em] text-blue-200">
                  Tu próximo clip está a un enlace
                </p>
                <h2 className="mt-3 font-display text-[2rem] font-semibold leading-[1.05] tracking-[-0.04em] sm:text-[2.6rem]">
                  Deja de mirar el timeline.
                </h2>
                <p className="mx-auto mt-4 max-w-lg text-[13px] leading-relaxed text-blue-100/85">
                  Crea tu cuenta gratis, pega tu primer enlace y mira los clips salir
                  solos. Si no te convence, no pagas nada.
                </p>
                <div className="mt-7 flex flex-col justify-center gap-3 sm:flex-row">
                  <button
                    type="button"
                    onClick={() => onStart("register")}
                    className="inline-flex items-center justify-center gap-2 rounded-xl bg-white px-6 py-3 text-[13px] font-bold text-blue-700 transition hover:bg-blue-50"
                  >
                    Empezar gratis
                    <IconArrowRight size={15} />
                  </button>
                  <button
                    type="button"
                    onClick={() => onStart("login")}
                    className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/25 bg-white/10 px-5 py-3 text-[13px] font-semibold text-white backdrop-blur transition hover:bg-white/20"
                  >
                    Ya tengo cuenta
                  </button>
                </div>
              </div>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-slate-200 bg-white">
        <div className="mx-auto w-full max-w-6xl px-4 py-12 sm:px-6">
          <div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-[1.4fr_1fr_1fr_1fr]">
            <div>
              <a href="#top" className="flex items-center gap-2.5" aria-label="Clipwise">
                <LogoMark />
                <span className="font-display text-lg font-bold tracking-tight text-slate-900">
                  Clipwise<span className="text-veru-ember">.</span>
                </span>
              </a>
              <p className="mt-3 max-w-xs text-[11px] leading-relaxed text-slate-400">
                Clips verticales automáticos desde YouTube, Kick y Twitch. Hecho para
                creadores que publican todos los días.
              </p>
            </div>

            <div>
              <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-slate-400">
                Producto
              </p>
              <ul className="mt-3 space-y-2 text-[11px] font-medium text-slate-500">
                <li><a href="#producto" className="transition hover:text-slate-900">Funciones</a></li>
                <li><a href="#como-funciona" className="transition hover:text-slate-900">Cómo funciona</a></li>
                <li><a href="#planes" className="transition hover:text-slate-900">Planes y precios</a></li>
                <li><a href="/docs" className="transition hover:text-slate-900">API</a></li>
              </ul>
            </div>

            <div>
              <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-slate-400">
                Recursos
              </p>
              <ul className="mt-3 space-y-2 text-[11px] font-medium text-slate-500">
                <li><a href="#faq" className="transition hover:text-slate-900">Preguntas frecuentes</a></li>
                <li><a href="mailto:support@clipwise.app" className="transition hover:text-slate-900">Soporte</a></li>
                <li><a href="/docs" className="transition hover:text-slate-900">Documentación</a></li>
                <li><a href="/browser.html" className="transition hover:text-slate-900">Render en navegador (beta)</a></li>
              </ul>
            </div>

            <div>
              <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-slate-400">
                Legal
              </p>
              <ul className="mt-3 space-y-2 text-[11px] font-medium text-slate-500">
                <li><a href="/terminos.html" className="transition hover:text-slate-900">Términos</a></li>
                <li><a href="/privacidad.html" className="transition hover:text-slate-900">Privacidad</a></li>
                <li><a href="mailto:support@clipwise.app" className="transition hover:text-slate-900">Contacto</a></li>
              </ul>
            </div>
          </div>

          <div className="mt-10 flex flex-col gap-3 border-t border-slate-100 pt-5 text-[10px] text-slate-400 sm:flex-row sm:items-center sm:justify-between">
            <span>© 2026 Clipwise. Todos los derechos reservados.</span>
            <span className="inline-flex items-center gap-1.5">
              <IconShield size={11} />
              FFmpeg · Whisper · Procesado en servidores aislados
            </span>
          </div>
        </div>
      </footer>
    </div>
  );
}
