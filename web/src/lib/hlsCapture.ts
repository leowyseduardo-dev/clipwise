import { attachHls, type HlsHandle } from "./hlsSource";

type FrameVideo = HTMLVideoElement & {
  requestVideoFrameCallback?: (callback: () => void) => number;
  cancelVideoFrameCallback?: (handle: number) => void;
};

export type CaptureOptions = {
  url: string;
  start: number;
  seconds: number;
  onProgress?: (value: number) => void;
};

function pickMimeType(): string {
  const candidates = [
    "video/mp4;codecs=avc1.640028,mp4a.40.2",
    "video/webm;codecs=vp9,opus",
    "video/webm;codecs=vp8,opus",
    "video/webm",
  ];
  return candidates.find((type) => MediaRecorder.isTypeSupported(type)) ?? "";
}

function waitForEvent(target: HTMLVideoElement, name: string, timeoutMs: number) {
  return new Promise<void>((resolve, reject) => {
    const timer = window.setTimeout(() => {
      cleanup();
      reject(new Error("El stream no respondió a tiempo."));
    }, timeoutMs);
    const done = () => {
      cleanup();
      resolve();
    };
    const cleanup = () => {
      window.clearTimeout(timer);
      target.removeEventListener(name, done);
    };
    target.addEventListener(name, done, { once: true });
  });
}

/**
 * Record a window of an HLS stream into a Blob that the Virocut engine can
 * render. A hidden video plays through the proxy, a canvas mirrors its frames,
 * and a Worker keeps the ticker alive when the tab is not focused.
 */
export async function captureHlsWindow(options: CaptureOptions): Promise<Blob> {
  const seconds = Math.max(0.5, Math.min(90, options.seconds));
  const video = document.createElement("video") as FrameVideo;
  video.muted = true;
  video.playsInline = true;
  video.crossOrigin = "anonymous";
  video.preload = "auto";
  video.style.position = "fixed";
  video.style.right = "0";
  video.style.bottom = "0";
  video.style.width = "160px";
  video.style.height = "90px";
  video.style.opacity = "0.01";
  video.style.pointerEvents = "none";
  video.style.zIndex = "-1";
  document.body.appendChild(video);

  let hls: HlsHandle | null = null;
  let audio: AudioContext | null = null;
  let worker: Worker | null = null;
  let recorder: MediaRecorder | null = null;
  let frameHandle = 0;
  let stopped = false;
  const supportsFrameCallback = "requestVideoFrameCallback" in video;

  try {
    hls = await attachHls(video, options.url);
    if (options.start > 0) {
      video.currentTime = options.start;
      await waitForEvent(video, "seeked", 20000);
    }
    await video.play();

    const canvas = document.createElement("canvas");
    canvas.width = 1080;
    canvas.height = 1920;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("Este navegador no permite renderizar el stream.");
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    const stream = canvas.captureStream(30);
    try {
      audio = new AudioContext();
      const source = audio.createMediaElementSource(video);
      const destination = audio.createMediaStreamDestination();
      source.connect(destination);
      destination.stream.getAudioTracks().forEach((track) => stream.addTrack(track));
      await audio.resume();
    } catch {
      // Audio capture is optional; the visual clip still renders.
    }

    const mimeType = pickMimeType();
    recorder = new MediaRecorder(stream, {
      ...(mimeType ? { mimeType } : {}),
      videoBitsPerSecond: 8_000_000,
      audioBitsPerSecond: 128_000,
    });
    const chunks: Blob[] = [];
    recorder.ondataavailable = (event) => {
      if (event.data.size) chunks.push(event.data);
    };
    const recorded = new Promise<Blob>((resolve, reject) => {
      recorder!.onstop = () =>
        resolve(new Blob(chunks, { type: mimeType.split(";")[0] || "video/webm" }));
      recorder!.onerror = () => reject(new Error("No se pudo grabar el stream."));
    });

    const tickerSource = `let id; onmessage=e=>{if(e.data==='start'){id=setInterval(()=>postMessage('tick'),33)}else{clearInterval(id)}};`;
    const workerUrl = URL.createObjectURL(
      new Blob([tickerSource], { type: "text/javascript" }),
    );
    worker = new Worker(workerUrl);
    URL.revokeObjectURL(workerUrl);

    let frameReady = true;
    const scheduleFrame = () => {
      if (video.requestVideoFrameCallback) {
        frameHandle = video.requestVideoFrameCallback(() => {
          frameReady = true;
        });
      }
    };
    scheduleFrame();

    const began = performance.now();
    worker.onmessage = () => {
      if (stopped) return;
      if (supportsFrameCallback && !frameReady) return;
      frameReady = false;
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      const elapsed = (performance.now() - began) / 1000;
      options.onProgress?.(Math.min(1, elapsed / seconds));
      if (elapsed >= seconds || video.currentTime >= options.start + seconds) {
        stopped = true;
        worker?.postMessage("stop");
        if (recorder?.state !== "inactive") recorder?.stop();
      } else {
        scheduleFrame();
      }
    };
    worker.postMessage("start");
    recorder.start(250);
    const blob = await recorded;
    options.onProgress?.(1);
    return blob;
  } finally {
    stopped = true;
    if (frameHandle && video.cancelVideoFrameCallback) {
      video.cancelVideoFrameCallback(frameHandle);
    }
    worker?.terminate();
    if (recorder?.state !== "inactive") recorder?.stop();
    await audio?.close().catch(() => undefined);
    hls?.destroy();
    video.pause();
    video.removeAttribute("src");
    video.load();
    video.remove();
  }
}
