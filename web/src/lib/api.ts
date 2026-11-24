import type {
  AISettings,
  CameraBox,
  Clip,
  Health,
  Job,
  LiveClip,
  LiveSession,
  OAuthStart,
  OAuthStatus,
  OptionsResponse,
  PublishPlatform,
  PublishRecord,
  PublishingConnections,
  PublishingSettings,
  PublishingSettingsInput,
  TikTokGrab,
} from "./types";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const data = (await response.json()) as { detail?: unknown };
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) {
      return data.detail
        .map((item) => (typeof item === "object" && item && "msg" in item ? String(item.msg) : ""))
        .filter(Boolean)
        .join(", ");
    }
  } catch {
    // Fall through to the status text.
  }
  return `Error ${response.status}`;
}

export async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new ApiError(await errorMessage(response), response.status);
  return (await response.json()) as T;
}

export async function sendJson<T>(path: string, method: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method,
    headers: body === undefined ? { Accept: "application/json" } : { "Content-Type": "application/json", Accept: "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) throw new ApiError(await errorMessage(response), response.status);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function getHealth(): Promise<Health> {
  return getJson<Health>("/api/health");
}

export function getAISettings(): Promise<AISettings> {
  return getJson<AISettings>("/api/ai/settings");
}

export function saveAISettings(body: { provider: AISettings["provider"]; model: string; base_url: string; api_key?: string; clear_key?: boolean }): Promise<AISettings> {
  return sendJson<AISettings>("/api/ai/settings", "PUT", body);
}

export function testAIConnection(): Promise<{ ok: boolean; message: string }> {
  return sendJson("/api/ai/test", "POST");
}

export function getOptions(): Promise<OptionsResponse> {
  return getJson<OptionsResponse>("/api/options");
}

export function activatePaypalSubscription(subscriptionId: string): Promise<{
  ok: boolean;
  plan: string;
  status: string;
  renews_at: string | null;
}> {
  return sendJson("/api/billing/paypal/activate", "POST", {
    subscription_id: subscriptionId,
  });
}

export function cancelPaypalSubscription(): Promise<{
  ok: boolean;
  status: string;
  active_until: string | null;
  plan: string;
}> {
  return sendJson("/api/billing/paypal/cancel", "POST");
}

export async function listJobs(): Promise<Job[]> {
  const data = await getJson<{ jobs: Job[] }>("/api/jobs");
  return data.jobs;
}

export function getJob(jobId: string): Promise<Job> {
  return getJson<Job>(`/api/jobs/${jobId}`);
}

export function cancelJob(jobId: string): Promise<Job> {
  return sendJson<Job>(`/api/jobs/${jobId}/cancel`, "POST");
}

export function retryJob(jobId: string): Promise<Job> {
  return sendJson<Job>(`/api/jobs/${jobId}/retry`, "POST");
}

export function deleteJob(jobId: string): Promise<{ deleted: boolean }> {
  return sendJson<{ deleted: boolean }>(`/api/jobs/${jobId}`, "DELETE");
}

export function retryClip(clipId: string): Promise<Clip> {
  return sendJson<Clip>(`/api/clips/${clipId}/render`, "POST");
}

export async function listTikTokGrabs(): Promise<{ grabs: TikTokGrab[] }> {
  return getJson<{ grabs: TikTokGrab[] }>("/api/tiktok/grabs");
}

export function getTikTokGrab(grabId: string): Promise<TikTokGrab> {
  return getJson<TikTokGrab>(`/api/tiktok/grabs/${grabId}`);
}

export function createTikTokGrab(payload: {
  url: string;
  title: string;
  auto_publish: boolean;
}): Promise<TikTokGrab> {
  return sendJson<TikTokGrab>("/api/tiktok/grabs", "POST", payload);
}

export function publishTikTokGrab(grabId: string): Promise<TikTokGrab> {
  return sendJson<TikTokGrab>(`/api/tiktok/grabs/${grabId}/retry`, "POST", {
    auto_publish: true,
  });
}

export async function listLiveSessions(): Promise<LiveSession[]> {
  const data = await getJson<{ sessions: LiveSession[] }>("/api/live/sessions");
  return data.sessions;
}

export function createLiveSession(url: string): Promise<LiveSession> {
  return sendJson<LiveSession>("/api/live/sessions", "POST", { url });
}

export function stopLiveSession(sessionId: string): Promise<LiveSession> {
  return sendJson<LiveSession>(`/api/live/sessions/${sessionId}/stop`, "POST");
}

export function resumeLiveSession(sessionId: string): Promise<LiveSession> {
  return sendJson<LiveSession>(`/api/live/sessions/${sessionId}/resume`, "POST");
}

export function deleteLiveSession(sessionId: string): Promise<void> {
  return sendJson<void>(`/api/live/sessions/${sessionId}`, "DELETE");
}

export function clipLiveSession(sessionId: string, seconds: number): Promise<LiveClip> {
  return sendJson<LiveClip>(`/api/live/sessions/${sessionId}/clip`, "POST", { seconds });
}

export function saveSubtitles(
  clipId: string,
  cues: { start: number; end: number; text: string }[],
): Promise<Clip> {
  return sendJson<Clip>(`/api/clips/${clipId}/subtitles`, "PUT", { cues });
}

export function regenerateClipDescription(clipId: string): Promise<Clip> {
  return sendJson<Clip>(`/api/clips/${clipId}/description`, "POST");
}

export function saveClipCopy(clipId: string, body: { title: string; description: string; caption: string }): Promise<Clip> {
  return sendJson<Clip>(`/api/clips/${clipId}/copy`, "PUT", body);
}

export function saveClipEdit(clipId: string, body: {
  subtitle_style: string; layout: string; remove_silences: boolean;
  dynamic_zoom: boolean; context_overlay: boolean;
  title_card?: string; title_card_seconds?: number;
  title_card_position?: string; title_card_style?: string;
  manual_cams?: CameraBox[];
  aspect?: string; caption_font?: string; caption_color?: string; accent_color?: string;
  music_level?: number | null; saturation?: number; brand_text?: string;
}): Promise<Clip> {
  return sendJson<Clip>(`/api/clips/${clipId}/edit`, "PUT", body);
}

export function clipFrameUrl(clipId: string, seconds = 0): string {
  return `/api/clips/${clipId}/frame.jpg?t=${Math.max(0, seconds).toFixed(2)}`;
}

export function clipSourceUrl(clipId: string): string {
  return `/api/clips/${clipId}/source.mp4`;
}

export function uploadBrowserRender(
  clipId: string,
  blob: Blob,
  options: Record<string, unknown>,
  onProgress?: (percent: number) => void,
): Promise<Clip> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("file", blob, `clip-${clipId}.mp4`);
    form.append("options", JSON.stringify(options));
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api/clips/${clipId}/browser-render`);
    xhr.responseType = "json";
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(xhr.response as Clip);
        return;
      }
      const detail = (xhr.response as { detail?: unknown } | null)?.detail;
      reject(
        new ApiError(
          typeof detail === "string" ? detail : `Error ${xhr.status}`,
          xhr.status,
        ),
      );
    };
    xhr.onerror = () =>
      reject(new ApiError("No se pudo subir el render al servidor.", 0));
    xhr.send(form);
  });
}

export function getPublishingSettings(): Promise<PublishingSettings> {
  return getJson<PublishingSettings>("/api/publishing/settings");
}

export function savePublishingSettings(
  input: PublishingSettingsInput,
): Promise<PublishingSettings> {
  return sendJson<PublishingSettings>("/api/publishing/settings", "PUT", input);
}

export function getPublishingConnections(): Promise<{
  connections: PublishingConnections;
  settings: PublishingSettings;
}> {
  return getJson<{
    connections: PublishingConnections;
    settings: PublishingSettings;
  }>("/api/publishing/connections");
}

export function startPublishingOAuth(platform: PublishPlatform): Promise<OAuthStart> {
  return sendJson<OAuthStart>(`/api/publishing/oauth/${platform}/start`, "POST");
}

export function getPublishingOAuthStatus(
  platform: PublishPlatform,
  state: string,
): Promise<OAuthStatus> {
  return getJson<OAuthStatus>(
    `/api/publishing/oauth/${platform}/status?state=${encodeURIComponent(state)}`,
  );
}

export function disconnectPublishing(
  platform: PublishPlatform,
): Promise<{ platform: PublishPlatform; connected: boolean }> {
  return sendJson<{ platform: PublishPlatform; connected: boolean }>(
    `/api/publishing/oauth/${platform}/disconnect`,
    "POST",
  );
}

export function publishClip(
  clipId: string,
  platform: PublishPlatform,
): Promise<PublishRecord> {
  return sendJson<PublishRecord>(`/api/clips/${clipId}/publish`, "POST", { platform });
}

export function listClipPublishRecords(clipId: string): Promise<{
  records: PublishRecord[];
  connections: PublishingConnections;
}> {
  return getJson<{
    records: PublishRecord[];
    connections: PublishingConnections;
  }>(`/api/clips/${clipId}/publish`);
}

export function createJob(
  form: FormData,
  onProgress?: (percent: number) => void,
): Promise<Job> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/jobs");
    xhr.responseType = "json";
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(xhr.response as Job);
        return;
      }
      const detail = (xhr.response as { detail?: unknown } | null)?.detail;
      reject(new ApiError(typeof detail === "string" ? detail : `Error ${xhr.status}`, xhr.status));
    };
    xhr.onerror = () => reject(new ApiError("No se pudo conectar con el servidor.", 0));
    xhr.send(form);
  });
}
