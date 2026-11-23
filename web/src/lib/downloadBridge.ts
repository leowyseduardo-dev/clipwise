type SaveDownloadResult = {
  ok?: boolean;
  cancelled?: boolean;
  error?: string;
  path?: string;
  size?: number;
};

type DesktopDownloadApi = {
  save_download?: (
    url: string,
    preferredName?: string,
  ) => Promise<SaveDownloadResult>;
};

type DesktopBridgeWindow = Window & {
  pywebview?: {
    api?: DesktopDownloadApi;
  };
  __ClipwiseDownloadBridge?: boolean;
};

const DOWNLOAD_PATH = /^\/api\/(?:clips|jobs|live|tiktok)\//;
const API_POLL_MS = 200;
const API_POLL_LIMIT = 300;

function showToast(message: string, isError: boolean): void {
  const id = "Clipwise-download-toast";
  let element = document.getElementById(id);
  if (!element) {
    element = document.createElement("div");
    element.id = id;
    element.style.position = "fixed";
    element.style.right = "24px";
    element.style.bottom = "24px";
    element.style.zIndex = "2147483647";
    element.style.maxWidth = "420px";
    element.style.padding = "12px 16px";
    element.style.borderRadius = "12px";
    element.style.fontFamily =
      "system-ui, -apple-system, Segoe UI, sans-serif";
    element.style.fontSize = "13px";
    element.style.lineHeight = "1.4";
    element.style.boxShadow = "0 12px 32px rgba(0,0,0,.45)";
    element.style.pointerEvents = "none";
    element.style.transition = "opacity .2s ease";
    document.body.appendChild(element);
  }
  element.textContent = message;
  element.style.background = isError ? "#3f1d24" : "#132a1f";
  element.style.color = isError ? "#fecdd3" : "#bbf7d0";
  element.style.border = isError ? "1px solid #7f1d1d" : "1px solid #14532d";
  element.style.opacity = "1";
  window.clearTimeout(
    (element as HTMLElement & { __ClipwiseTimer?: number })
      .__ClipwiseTimer,
  );
  (element as HTMLElement & { __ClipwiseTimer?: number }).__ClipwiseTimer =
    window.setTimeout(
      () => {
        element!.style.opacity = "0";
      },
      isError ? 6000 : 3000,
    );
}

function install(): void {
  const desktopWindow = window as DesktopBridgeWindow;
  const api = desktopWindow.pywebview?.api;
  if (!api?.save_download) {
    return;
  }
  if (desktopWindow.__ClipwiseDownloadBridge) {
    return;
  }
  desktopWindow.__ClipwiseDownloadBridge = true;

  let busy = false;

  document.addEventListener(
    "click",
    (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0) {
        return;
      }
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
        return;
      }
      const target = event.target;
      if (!(target instanceof Element)) {
        return;
      }
      const anchor = target.closest("a[href]");
      if (!(anchor instanceof HTMLAnchorElement)) {
        return;
      }
      const url = new URL(anchor.href, window.location.href);
      if (url.origin !== window.location.origin) {
        return;
      }
      if (!DOWNLOAD_PATH.test(url.pathname)) {
        return;
      }

      event.preventDefault();
      event.stopPropagation();
      if (busy) {
        return;
      }
      busy = true;

      const previousOpacity = anchor.style.opacity;
      anchor.style.opacity = "0.55";
      anchor.setAttribute("aria-busy", "true");
      const preferred = anchor.getAttribute("download") ?? "";
      showToast("Preparando descarga...", false);

      api
        .save_download!(url.pathname + url.search, preferred)
        .then((result) => {
          if (result?.ok) {
            showToast("Descarga completada", false);
          } else if (!result?.cancelled) {
            showToast(
              "No se pudo descargar" +
                (result?.error ? `: ${result.error}` : ""),
              true,
            );
          }
        })
        .catch((error: unknown) => {
          const message =
            error instanceof Error ? error.message : String(error);
          showToast(`No se pudo descargar: ${message}`, true);
        })
        .finally(() => {
          busy = false;
          anchor.style.opacity = previousOpacity;
          anchor.removeAttribute("aria-busy");
        });
    },
    true,
  );
}

export function installDownloadBridge(): void {
  const desktopWindow = window as DesktopBridgeWindow;
  if (desktopWindow.__ClipwiseDownloadBridge) {
    return;
  }

  let attempts = 0;
  const waitForApi = () => {
    if (desktopWindow.pywebview?.api?.save_download) {
      install();
      return;
    }
    attempts += 1;
    if (attempts >= API_POLL_LIMIT) {
      return;
    }
    window.setTimeout(waitForApi, API_POLL_MS);
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", waitForApi, { once: true });
  } else {
    waitForApi();
  }
}
