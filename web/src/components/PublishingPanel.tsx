import {useAccount} from "./AccountGate";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  disconnectPublishing,
  getPublishingConnections,
  getPublishingOAuthStatus,
  listClipPublishRecords,
  publishClip,
  savePublishingSettings,
  startPublishingOAuth,
} from "../lib/api";
import type {
  Clip,
  OAuthStart,
  PublishPlatform,
  PublishRecord,
  PublishingAccount,
  PublishingConnections,
  PublishingSettings,
  PublishingSettingsInput,
} from "../lib/types";
import {
  IconAlert,
  IconCheck,
  IconCopy,
  IconLoader,
  IconRefresh,
  IconSettings,
  IconTikTok,
  IconUpload,
  IconX,
  IconYouTube,
} from "./icons";

interface PublishingPanelProps {
  clip: Clip;
  initialPlatform?: PublishPlatform;
  onError: (message: string) => void;
}

interface SettingsForm {
  youtube_client_id: string;
  youtube_client_secret: string;
  tiktok_client_key: string;
  tiktok_client_secret: string;
  redirect_port: string;
  youtube_privacy: string;
  tiktok_privacy: string;
}

interface Banner {
  kind: "success" | "info" | "error";
  text: string;
}

const PLATFORM_INFO: Record<
  PublishPlatform,
  { label: string; icon: typeof IconYouTube; tabActive: string; tabIdle: string; iconClass: string }
> = {
  youtube: {
    label: "YouTube",
    icon: IconYouTube,
    tabActive: "border-rose-400/40 bg-rose-500/15 text-rose-100",
    tabIdle: "border-transparent text-veru-paper/50 hover:bg-veru-paper/5 hover:text-veru-paper/80",
    iconClass: "border-rose-400/25 bg-rose-500/10 text-rose-200",
  },
  tiktok: {
    label: "TikTok",
    icon: IconTikTok,
    tabActive: "border-veru-blush/40 bg-veru-blush/15 text-veru-paper",
    tabIdle: "border-transparent text-veru-paper/50 hover:bg-veru-paper/5 hover:text-veru-paper/80",
    iconClass: "border-veru-blush/25 bg-veru-blush/10 text-veru-blush",
  },
};

const YOUTUBE_PRIVACY = [
  { value: "private", label: "Privado" },
  { value: "unlisted", label: "No listado" },
  { value: "public", label: "Público" },
];

const TIKTOK_PRIVACY = [
  { value: "SELF_ONLY", label: "Solo yo" },
  { value: "PUBLIC_TO_EVERYONE", label: "Todos" },
  { value: "MUTUAL_FOLLOW_FRIENDS", label: "Amigos" },
  { value: "FOLLOWER_OF_CREATOR", label: "Seguidores" },
];

const STATUS_LABEL: Record<string, string> = {
  queued: "En cola",
  uploading: "Subiendo",
  processing: "Procesando",
  published: "Publicado",
  failed: "Error",
};

function emptyForm(): SettingsForm {
  return {
    youtube_client_id: "",
    youtube_client_secret: "",
    tiktok_client_key: "",
    tiktok_client_secret: "",
    redirect_port: "53682",
    youtube_privacy: "private",
    tiktok_privacy: "SELF_ONLY",
  };
}

function formFromSettings(settings: PublishingSettings): SettingsForm {
  return {
    youtube_client_id: settings.youtube_client_id || "",
    youtube_client_secret: "",
    tiktok_client_key: settings.tiktok_client_key || "",
    tiktok_client_secret: "",
    redirect_port: String(settings.redirect_port || 53682),
    youtube_privacy: settings.youtube_privacy || "private",
    tiktok_privacy: settings.tiktok_privacy || "SELF_ONLY",
  };
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

function isActiveStatus(status: string): boolean {
  return status === "queued" || status === "uploading" || status === "processing";
}

export function PublishingPanel({
  clip,
  initialPlatform,
  onError,
}: PublishingPanelProps) {
  const cloud=useAccount();
  const [settings, setSettings] = useState<PublishingSettings | null>(null);
  const [connections, setConnections] = useState<PublishingConnections>({
    youtube: null,
    tiktok: null,
  });
  const [records, setRecords] = useState<PublishRecord[]>([]);
  const [platform, setPlatform] = useState<PublishPlatform>(
    initialPlatform ?? "youtube",
  );
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<
    "connect" | "publish" | "settings" | "disconnect" | null
  >(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [form, setForm] = useState<SettingsForm>(emptyForm);
  const [oauth, setOauth] = useState<OAuthStart | null>(null);
  const [banner, setBanner] = useState<Banner | null>(null);
  const [copiedRedirect, setCopiedRedirect] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [connectionData, recordData] = await Promise.all([
        getPublishingConnections(),
        listClipPublishRecords(clip.id),
      ]);
      setSettings(connectionData.settings);
      setConnections(connectionData.connections);
      setRecords(recordData.records);
      setForm(formFromSettings(connectionData.settings));
    } catch (error) {
      onError(
        errorMessage(error, "No se pudo cargar la configuración de publicación."),
      );
    } finally {
      setLoading(false);
    }
  }, [clip.id, onError]);

  useEffect(() => {
    void load();
  }, [load]);

  const info = PLATFORM_INFO[platform];
  const account: PublishingAccount | null = connections[platform];
  const configured = settings
    ? platform === "youtube"
      ? settings.youtube_configured
      : settings.tiktok_configured
    : false;

  const platformRecords = useMemo(
    () => records.filter((record) => record.platform === platform),
    [records, platform],
  );
  const activeRecord = platformRecords.find((record) =>
    isActiveStatus(record.status),
  );
  const latestRecord = platformRecords[0] ?? null;
  const canPublish = Boolean(clip.video_url) && clip.status === "ready";

  useEffect(() => {
    if (!activeRecord) return;
    let cancelled = false;
    const timer = window.setInterval(async () => {
      try {
        const data = await listClipPublishRecords(clip.id);
        if (cancelled) return;
        setRecords(data.records);
        setConnections(data.connections);
      } catch {
        // Keep the last known progress; the next tick retries.
      }
    }, 1800);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [activeRecord?.id, clip.id]);

  useEffect(() => {
    if (!oauth) return;
    let cancelled = false;
    const timer = window.setInterval(async () => {
      try {
        const status = await getPublishingOAuthStatus(oauth.platform, oauth.state);
        if (cancelled) return;
        if (status.status === "success") {
          setOauth(null);
          setBusy(null);
          setBanner({
            kind: "success",
            text: status.account?.account_name
              ? `Conectado como ${status.account.account_name}.`
              : "Cuenta conectada.",
          });
          const data = await getPublishingConnections();
          if (cancelled) return;
          setSettings(data.settings);
          setConnections(data.connections);
          setForm(formFromSettings(data.settings));
        } else if (status.status === "error") {
          setOauth(null);
          setBusy(null);
          setBanner({
            kind: "error",
            text: status.message || "No se pudo conectar la cuenta.",
          });
          onError(status.message || "No se pudo conectar la cuenta.");
        }
      } catch (error) {
        if (cancelled) return;
        setOauth(null);
        setBusy(null);
        onError(errorMessage(error, "No se pudo comprobar la conexión."));
      }
    }, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [oauth, onError]);

  useEffect(() => {
    if (!settings || !initialPlatform) return;
    const ready =
      initialPlatform === "youtube"
        ? settings.youtube_configured
        : settings.tiktok_configured;
    if (!ready) setSettingsOpen(true);
  }, [settings, initialPlatform]);

  function openSettings() {
    if (settings) setForm(formFromSettings(settings));
    setSettingsOpen(true);
  }

  async function handleConnect() {
    if (!settings) return;
    if (!configured) {
      openSettings();
      setBanner({
        kind: "info",
        text: `Añade las credenciales de ${info.label} y guarda los ajustes.`,
      });
      return;
    }
    setBusy("connect");
    setBanner(null);
    try {
      const start = await startPublishingOAuth(platform);
      setOauth(start);
      setBanner({
        kind: "info",
        text: start.browser_opened
          ? `Autoriza ${info.label} en el navegador. Esta ventana se actualizará sola.`
          : `Abre el enlace de autorización de ${info.label}.`,
      });
    } catch (error) {
      setBusy(null);
      onError(errorMessage(error, `No se pudo iniciar la conexión con ${info.label}.`));
    }
  }

  async function handleDisconnect() {
    if (!account) return;
    const label = account.account_name || info.label;
    if (!window.confirm(`¿Desconectar ${label} de Clipwise?`)) return;
    setBusy("disconnect");
    try {
      await disconnectPublishing(platform);
      setConnections((previous) => ({ ...previous, [platform]: null }));
      setBanner({ kind: "info", text: `${info.label} desconectado.` });
    } catch (error) {
      onError(errorMessage(error, `No se pudo desconectar ${info.label}.`));
    } finally {
      setBusy(null);
    }
  }

  async function handlePublish() {
    if (!account) {
      void handleConnect();
      return;
    }
    setBusy("publish");
    setBanner(null);
    try {
      const record = await publishClip(clip.id, platform);
      setRecords((previous) => [
        record,
        ...previous.filter((item) => item.id !== record.id),
      ]);
      setBanner({ kind: "info", text: `Subiendo a ${info.label}…` });
    } catch (error) {
      onError(errorMessage(error, `No se pudo publicar en ${info.label}.`));
    } finally {
      setBusy(null);
    }
  }

  async function handleSaveSettings() {
    const port = Number(form.redirect_port);
    if (!Number.isInteger(port) || port < 1024 || port > 65535) {
      onError("El puerto de redirección debe estar entre 1024 y 65535.");
      return;
    }
    setBusy("settings");
    try {
      const payload: PublishingSettingsInput = {
        youtube_client_id: form.youtube_client_id.trim(),
        youtube_client_secret: form.youtube_client_secret,
        tiktok_client_key: form.tiktok_client_key.trim(),
        tiktok_client_secret: form.tiktok_client_secret,
        redirect_port: port,
        youtube_privacy: form.youtube_privacy,
        tiktok_privacy: form.tiktok_privacy,
      };
      const updated = await savePublishingSettings(payload);
      setSettings(updated);
      setForm(formFromSettings(updated));
      setSettingsOpen(false);
      setBanner({
        kind: "success",
        text: "Ajustes de publicación guardados.",
      });
    } catch (error) {
      onError(errorMessage(error, "No se pudieron guardar los ajustes."));
    } finally {
      setBusy(null);
    }
  }

  async function copyRedirectUri() {
    if (!settings) return;
    try {
      await navigator.clipboard.writeText(settings.redirect_uri);
      setCopiedRedirect(true);
      window.setTimeout(() => setCopiedRedirect(false), 1800);
    } catch {
      onError("El navegador bloqueó el acceso al portapapeles.");
    }
  }

  if (loading) {
    return (
      <div className="rounded-2xl border border-veru-paper/10 bg-veru-paper/[0.03] p-4">
        <p className="flex items-center gap-2 text-[11px] text-veru-paper/50">
          <IconLoader size={13} className="animate-spin" />
          Cargando publicación automática…
        </p>
      </div>
    );
  }

  if (!settings) {
    return (
      <div className="rounded-2xl border border-rose-400/20 bg-rose-500/10 p-4 text-[11px] leading-relaxed text-rose-200">
        <p className="flex items-start gap-2">
          <IconAlert size={14} className="mt-0.5 shrink-0" />
          No se pudo cargar la configuración de publicación.
        </p>
        <button
          type="button"
          onClick={() => void load()}
          className="mt-2 inline-flex items-center gap-1 rounded-lg border border-rose-300/25 bg-rose-500/10 px-2 py-1 text-[10px] font-semibold text-rose-100 transition hover:bg-rose-500/20"
        >
          <IconRefresh size={11} />
          Reintentar
        </button>
      </div>
    );
  }

  const PublishIcon = info.icon;
  const buttonLabel = !configured
    ? `Configurar ${info.label}`
    : !account
      ? `Conectar ${info.label}`
      : latestRecord?.status === "published"
        ? `Publicar de nuevo en ${info.label}`
        : `Publicar en ${info.label}`;
  const publishDisabled =
    busy !== null ||
    (Boolean(account) && (!canPublish || Boolean(activeRecord)));

  return (
    <div className="rounded-2xl border border-veru-paper/10 bg-veru-paper/[0.03] p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h4 className="text-[11px] font-semibold uppercase tracking-wider text-veru-paper/50">
            Publicación automática
          </h4>
          <p className="mt-1 text-[10px] leading-relaxed text-veru-paper/35">
            Sube este clip a tu cuenta sin salir de Clipwise.
          </p>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => void load()}
            disabled={busy !== null}
            className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[10px] text-veru-paper/50 transition hover:bg-veru-paper/5 hover:text-veru-paper/90 disabled:opacity-40"
          >
            <IconRefresh size={11} />
            Actualizar
          </button>
          <button
            type="button"
            hidden={cloud.hosted}
            onClick={openSettings}
            className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[10px] text-veru-paper/50 transition hover:bg-veru-paper/5 hover:text-veru-paper/90"
          >
            <IconSettings size={11} />
            Ajustes
          </button>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-1 rounded-2xl border border-veru-paper/10 bg-black/20 p-1">
        {(Object.keys(PLATFORM_INFO) as PublishPlatform[]).map((id) => {
          const item = PLATFORM_INFO[id];
          const TabIcon = item.icon;
          const connected = Boolean(connections[id]);
          return (
            <button
              key={id}
              type="button"
              onClick={() => setPlatform(id)}
              aria-pressed={platform === id}
              className={`inline-flex items-center justify-center gap-1.5 rounded-xl border px-2 py-2 text-[11px] font-semibold transition ${
                platform === id ? item.tabActive : item.tabIdle
              }`}
            >
              <TabIcon size={13} />
              {item.label}
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  connected ? "bg-emerald-400" : "bg-veru-paper/25"
                }`}
              />
            </button>
          );
        })}
      </div>

      <div className="mt-3 rounded-2xl border border-veru-paper/10 bg-black/20 p-3">
        {account ? (
          <div className="flex items-start justify-between gap-2">
            <div className="flex min-w-0 items-center gap-2.5">
              <span
                className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border ${info.iconClass}`}
              >
                <PublishIcon size={15} />
              </span>
              <div className="min-w-0">
                <p className="truncate text-xs font-semibold text-veru-paper">
                  {account.account_name || `${info.label} conectado`}
                </p>
                <p className="text-[10px] text-veru-paper/35">
                  Cuenta conectada en este equipo
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => void handleDisconnect()}
              disabled={busy !== null}
              className="shrink-0 rounded-lg px-2 py-1 text-[10px] text-veru-paper/50 transition hover:bg-veru-paper/5 hover:text-rose-200 disabled:opacity-40"
            >
              Desconectar
            </button>
          </div>
        ) : (
          <div className="flex items-start gap-2.5">
            <span
              className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border ${info.iconClass}`}
            >
              <PublishIcon size={15} />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-semibold text-veru-paper/80">
                Sin cuenta de {info.label}
              </p>
              <p className="mt-0.5 text-[10px] leading-relaxed text-veru-paper/35">
                Conecta tu cuenta para subir el clip sin salir de la app.
              </p>
            </div>
          </div>
        )}
      </div>

      {banner && (
        <div
          className={`mt-3 flex items-start gap-2 rounded-xl border px-3 py-2 text-[10px] leading-relaxed ${
            banner.kind === "error"
              ? "border-rose-400/20 bg-rose-500/10 text-rose-200"
              : banner.kind === "success"
                ? "border-emerald-400/20 bg-emerald-500/10 text-emerald-200"
                : "border-veru-blush/20 bg-veru-blush/10 text-veru-paper"
          }`}
        >
          {banner.kind === "error" ? (
            <IconAlert size={12} className="mt-0.5 shrink-0" />
          ) : banner.kind === "success" ? (
            <IconCheck size={12} className="mt-0.5 shrink-0" />
          ) : (
            <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-veru-blush" />
          )}
          <span>{banner.text}</span>
        </div>
      )}

      {oauth && (
        <div className="mt-3 rounded-xl border border-veru-blush/20 bg-veru-blush/[0.06] px-3 py-2.5">
          <p className="text-[11px] font-medium text-veru-paper">
            Esperando autorización de {PLATFORM_INFO[oauth.platform].label}…
          </p>
          <a
            href={oauth.auth_url}
            target="_blank"
            rel="noreferrer"
            className="mt-1 inline-flex text-[10px] font-semibold text-veru-blush underline decoration-veru-blush/30 underline-offset-2 transition hover:text-veru-paper"
          >
            Abrir la pantalla de autorización
          </a>
          <p className="mt-1 text-[10px] leading-relaxed text-veru-blush/50">
            Si el navegador no se abrió, usa este enlace. La app detecta la
            conexión automáticamente.
          </p>
        </div>
      )}

      {activeRecord && (
        <div className="mt-3 rounded-xl border border-veru-ember/20 bg-veru-ember/[0.07] px-3 py-2.5">
          <div className="flex items-center justify-between gap-2 text-[11px]">
            <span className="inline-flex items-center gap-1.5 text-veru-blush">
              <IconLoader size={12} className="animate-spin" />
              {activeRecord.status === "processing"
                ? `Procesando en ${info.label}`
                : STATUS_LABEL[activeRecord.status] ?? activeRecord.status}
            </span>
            <span className="tabular-nums text-veru-blush/80">
              {Math.round(activeRecord.progress)}%
            </span>
          </div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-veru-paper/10">
            <div
              className={`h-full rounded-full transition-[width] duration-500 ${
                platform === "youtube"
                  ? "bg-gradient-to-r from-rose-500 to-orange-400"
                  : "bg-gradient-to-r from-veru-blush to-veru-ember"
              }`}
              style={{
                width: `${Math.max(3, Math.min(100, activeRecord.progress))}%`,
              }}
            />
          </div>
          {activeRecord.status === "processing" && (
            <p className="mt-1.5 text-[10px] leading-relaxed text-veru-blush/60">
              {info.label} está procesando el video. Esto puede tardar un
              minuto.
            </p>
          )}
        </div>
      )}

      {!activeRecord && latestRecord?.status === "published" && latestRecord.remote_url && (
        <a
          href={latestRecord.remote_url}
          target="_blank"
          rel="noreferrer"
          className="mt-3 inline-flex w-full items-center justify-center gap-1.5 rounded-xl border border-emerald-400/25 bg-emerald-500/10 px-3 py-2 text-[11px] font-semibold text-emerald-100 transition hover:bg-emerald-500/20"
        >
          <IconCheck size={12} />
          Ver en {info.label}
        </a>
      )}

      {!activeRecord && latestRecord?.status === "failed" && latestRecord.error && (
        <div className="mt-3 flex items-start gap-2 rounded-xl border border-rose-400/20 bg-rose-500/10 px-3 py-2 text-[10px] leading-relaxed text-rose-200">
          <IconAlert size={12} className="mt-0.5 shrink-0" />
          <span className="break-words">{latestRecord.error}</span>
        </div>
      )}

      <button
        type="button"
        onClick={() => {
          if (!account) void handleConnect();
          else void handlePublish();
        }}
        disabled={publishDisabled}
        className="button-primary mt-3 w-full py-2.5 text-xs"
      >
        {busy === "publish" || busy === "connect" ? (
          <IconLoader size={13} className="animate-spin" />
        ) : account ? (
          <IconUpload size={13} />
        ) : (
          <PublishIcon size={13} />
        )}
        {buttonLabel}
      </button>

      {!canPublish && (
        <p className="mt-1.5 text-center text-[10px] text-veru-paper/35">
          El clip estará disponible para publicar cuando termine el render.
        </p>
      )}

      {settingsOpen && cloud.hosted && <p className="text-xs">El administrador debe configurar las credenciales de {info.label} en el servidor.</p>}
      {settingsOpen && !cloud.hosted && (
        <div className="mt-3 rounded-2xl border border-veru-ember/20 bg-veru-ember/[0.05] p-3.5">
          <div className="flex items-center justify-between gap-2">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-veru-blush">
              Credenciales de publicación
            </p>
            <button
              type="button"
              onClick={() => setSettingsOpen(false)}
              className="rounded-lg p-1 text-veru-blush/60 transition hover:bg-veru-paper/5 hover:text-veru-paper"
              aria-label="Cerrar ajustes"
            >
              <IconX size={13} />
            </button>
          </div>

          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <label className="block sm:col-span-2">
              <span className="mb-1 block text-[10px] font-medium text-veru-paper/50">
                Client ID de YouTube
              </span>
              <input
                type="text"
                value={form.youtube_client_id}
                onChange={(event) =>
                  setForm((previous) => ({
                    ...previous,
                    youtube_client_id: event.target.value,
                  }))
                }
                placeholder="...apps.googleusercontent.com"
                className="field px-3 py-2 text-xs"
              />
            </label>
            <label className="block sm:col-span-2">
              <span className="mb-1 block text-[10px] font-medium text-veru-paper/50">
                Client Secret de YouTube
              </span>
              <input
                type="password"
                value={form.youtube_client_secret}
                onChange={(event) =>
                  setForm((previous) => ({
                    ...previous,
                    youtube_client_secret: event.target.value,
                  }))
                }
                placeholder={
                  settings.youtube_client_secret_set
                    ? "Guardado · deja vacío para conservar"
                    : "Sin guardar"
                }
                className="field px-3 py-2 text-xs"
              />
            </label>
            <label className="block sm:col-span-2">
              <span className="mb-1 block text-[10px] font-medium text-veru-paper/50">
                Client Key de TikTok
              </span>
              <input
                type="text"
                value={form.tiktok_client_key}
                onChange={(event) =>
                  setForm((previous) => ({
                    ...previous,
                    tiktok_client_key: event.target.value,
                  }))
                }
                placeholder="Client key de tu app de TikTok"
                className="field px-3 py-2 text-xs"
              />
            </label>
            <label className="block sm:col-span-2">
              <span className="mb-1 block text-[10px] font-medium text-veru-paper/50">
                Client Secret de TikTok
              </span>
              <input
                type="password"
                value={form.tiktok_client_secret}
                onChange={(event) =>
                  setForm((previous) => ({
                    ...previous,
                    tiktok_client_secret: event.target.value,
                  }))
                }
                placeholder={
                  settings.tiktok_client_secret_set
                    ? "Guardado · deja vacío para conservar"
                    : "Sin guardar"
                }
                className="field px-3 py-2 text-xs"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-[10px] font-medium text-veru-paper/50">
                Privacidad de YouTube
              </span>
              <select
                value={form.youtube_privacy}
                onChange={(event) =>
                  setForm((previous) => ({
                    ...previous,
                    youtube_privacy: event.target.value,
                  }))
                }
                className="field px-3 py-2 text-xs"
              >
                {YOUTUBE_PRIVACY.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="mb-1 block text-[10px] font-medium text-veru-paper/50">
                Privacidad de TikTok
              </span>
              <select
                value={form.tiktok_privacy}
                onChange={(event) =>
                  setForm((previous) => ({
                    ...previous,
                    tiktok_privacy: event.target.value,
                  }))
                }
                className="field px-3 py-2 text-xs"
              >
                {TIKTOK_PRIVACY.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="mb-1 block text-[10px] font-medium text-veru-paper/50">
                Puerto local para OAuth
              </span>
              <input
                type="number"
                min={1024}
                max={65535}
                value={form.redirect_port}
                onChange={(event) =>
                  setForm((previous) => ({
                    ...previous,
                    redirect_port: event.target.value,
                  }))
                }
                className="field px-3 py-2 text-xs"
              />
            </label>
          </div>

          <div className="mt-3 rounded-xl border border-veru-paper/10 bg-black/30 px-3 py-2">
            <div className="flex items-center justify-between gap-2">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-veru-paper/35">
                Redirect URI
              </p>
              <button
                type="button"
                onClick={() => void copyRedirectUri()}
                className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[10px] text-veru-paper/50 transition hover:bg-veru-paper/5 hover:text-veru-paper/90"
              >
                {copiedRedirect ? <IconCheck size={11} /> : <IconCopy size={11} />}
                {copiedRedirect ? "Copiada" : "Copiar"}
              </button>
            </div>
            <p className="mt-1 break-all font-mono text-[10px] leading-relaxed text-veru-blush/80">
              {settings.redirect_uri}
            </p>
            <p className="mt-1 text-[10px] leading-relaxed text-veru-paper/35">
              Regístrala exactamente en Google Cloud y TikTok for Developers. Si
              cambias el puerto, guarda y vuelve a registrarla.
            </p>
          </div>

          <div className="mt-3 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setSettingsOpen(false)}
              className="button-ghost"
            >
              Cancelar
            </button>
            <button
              type="button"
              onClick={() => void handleSaveSettings()}
              disabled={busy === "settings"}
              className="button-primary px-4 py-2 text-xs"
            >
              {busy === "settings" ? (
                <IconLoader size={12} className="animate-spin" />
              ) : (
                <IconCheck size={12} />
              )}
              Guardar ajustes
            </button>
          </div>

          <details className="mt-3 rounded-xl border border-veru-paper/10 bg-black/20 px-3 py-2">
            <summary className="cursor-pointer text-[10px] font-semibold text-veru-paper/50 transition hover:text-veru-paper/80">
              Cómo obtener las credenciales
            </summary>
            <div className="mt-2 space-y-2 text-[10px] leading-relaxed text-veru-paper/35">
              <p>
                <span className="font-semibold text-veru-paper/70">YouTube:</span>{" "}
                Google Cloud Console → habilita YouTube Data API v3 →
                Credenciales → ID de cliente OAuth → Aplicación de escritorio.
                Alcances: youtube.upload y youtube.readonly.
              </p>
              <p>
                <span className="font-semibold text-veru-paper/70">TikTok:</span>{" "}
                TikTok for Developers → Content Posting API → Direct Post →
                scope video.publish. La app debe estar aprobada para publicar
                directamente.
              </p>
              <p>
                <span className="font-semibold text-veru-paper/70">Cuota YouTube:</span>{" "}
                cada videos.insert consume 1600 unidades; la cuota diaria por
                defecto permite unas 6 subidas.
              </p>
            </div>
          </details>
        </div>
      )}
    </div>
  );
}
