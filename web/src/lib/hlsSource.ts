export function hlsProxyUrl(raw: string): string {
  return `/api/public/hls?u=${encodeURIComponent(raw.trim())}`;
}

export type HlsHandle = {
  destroy: () => void;
};

function waitForMetadata(video: HTMLVideoElement, timeoutMs: number): Promise<void> {
  return new Promise((resolve, reject) => {
    if (video.readyState >= 1 && Number.isFinite(video.duration)) {
      resolve();
      return;
    }
    const timer = window.setTimeout(() => {
      cleanup();
      reject(new Error("El stream tardó demasiado en responder."));
    }, timeoutMs);
    const done = () => {
      cleanup();
      resolve();
    };
    const fail = () => {
      cleanup();
      reject(new Error("No se pudo cargar el stream."));
    };
    const cleanup = () => {
      window.clearTimeout(timer);
      video.removeEventListener("loadedmetadata", done);
      video.removeEventListener("error", fail);
    };
    video.addEventListener("loadedmetadata", done);
    video.addEventListener("error", fail);
  });
}

/** Attach a Kick/Twitch HLS URL through the same-origin Clipwise proxy. */
export async function attachHls(
  video: HTMLVideoElement,
  raw: string,
): Promise<HlsHandle> {
  const url = hlsProxyUrl(raw);
  if (video.canPlayType("application/vnd.apple.mpegurl")) {
    video.src = url;
    await waitForMetadata(video, 20000);
    return { destroy: () => video.removeAttribute("src") };
  }
  const { default: Hls } = await import("hls.js");
  if (!Hls.isSupported()) {
    throw new Error("Este navegador no puede reproducir HLS.");
  }
  const hls = new Hls({
    maxBufferLength: 20,
    enableWorker: true,
    lowLatencyMode: false,
  });
  hls.loadSource(url);
  hls.attachMedia(video);
  await waitForMetadata(video, 20000);
  return { destroy: () => hls.destroy() };
}
