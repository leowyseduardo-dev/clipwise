import { useEffect, useRef, useState } from "react";

import { IconAlert, IconLoader } from "./icons";

type PayPalActions = {
  subscription: {
    create: (options: Record<string, unknown>) => Promise<string>;
  };
};

type PayPalButtons = {
  style?: Record<string, unknown>;
  createSubscription: (
    data: unknown,
    actions: PayPalActions,
  ) => Promise<string>;
  onApprove: (data: { subscriptionID: string }) => Promise<void>;
  onCancel?: () => void;
  onError?: (error: unknown) => void;
};

type PayPalNamespace = {
  Buttons: (config: PayPalButtons) => {
    isEligible: () => boolean;
    render: (target: HTMLElement) => Promise<void>;
  };
};

declare global {
  interface Window {
    paypal?: PayPalNamespace;
  }
}

let sdkPromise: Promise<void> | null = null;
let sdkKey = "";

function loadSdk(clientId: string, mode: "live" | "sandbox"): Promise<void> {
  if (window.paypal?.Buttons) return Promise.resolve();
  const key = mode + ":" + clientId;
  if (sdkPromise && sdkKey === key) return sdkPromise;
  sdkKey = key;
  sdkPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(
      "script[data-clipwise-paypal]",
    );
    if (existing) {
      existing.addEventListener("load", () => resolve(), { once: true });
      existing.addEventListener(
        "error",
        () => reject(new Error("No se pudo cargar PayPal.")),
        { once: true },
      );
      return;
    }
    const script = document.createElement("script");
    const host =
      mode === "sandbox" ? "www.sandbox.paypal.com" : "www.paypal.com";
    script.src =
      "https://" +
      host +
      "/sdk/js?client-id=" +
      encodeURIComponent(clientId) +
      "&vault=true&intent=subscription&currency=USD";
    script.async = true;
    script.dataset.clipwisePaypal = "1";
    script.onload = () => resolve();
    script.onerror = () => {
      sdkPromise = null;
      reject(new Error("No se pudo cargar PayPal. Revisa tu conexion."));
    };
    document.head.appendChild(script);
  });
  return sdkPromise;
}

export function PayPalSubscribeButton({
  clientId,
  mode,
  planId,
  planName,
  teamId,
  disabled,
  onActivated,
  onError,
}: {
  clientId: string;
  mode: "live" | "sandbox";
  planId: string;
  planName: string;
  teamId: string;
  disabled?: boolean;
  onActivated: (subscriptionId: string) => Promise<void>;
  onError: (message: string) => void;
}) {
  const target = useRef<HTMLDivElement>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState("");
  const callbacks = useRef({ onActivated, onError });
  callbacks.current = { onActivated, onError };

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setFailed("");
    if (!clientId || !planId || !teamId) {
      setLoading(false);
      setFailed("PayPal no esta configurado en el servidor.");
      return;
    }
    loadSdk(clientId, mode)
      .then(() => {
        if (cancelled || !target.current || !window.paypal) return;
        target.current.innerHTML = "";
        const buttons = window.paypal.Buttons({
          style: {
            shape: "rect",
            color: "gold",
            layout: "vertical",
            label: "subscribe",
            height: 40,
          },
          createSubscription: (_data, actions) =>
            actions.subscription.create({
              plan_id: planId,
              custom_id: teamId,
            }),
          onApprove: async (data) => {
            try {
              await callbacks.current.onActivated(data.subscriptionID);
            } catch (error) {
              callbacks.current.onError(
                error instanceof Error
                  ? error.message
                  : "No se pudo activar el plan.",
              );
              throw error;
            }
          },
          onCancel: () =>
            callbacks.current.onError(
              "Pago cancelado. No se hizo ningun cargo.",
            ),
          onError: (error) =>
            callbacks.current.onError(
              error instanceof Error
                ? error.message
                : "PayPal devolvio un error.",
            ),
        });
        if (!buttons.isEligible()) {
          setLoading(false);
          setFailed("PayPal no esta disponible en este navegador.");
          return;
        }
        return buttons.render(target.current).then(() => {
          if (!cancelled) setLoading(false);
        });
      })
      .catch((error) => {
        if (!cancelled) {
          setLoading(false);
          setFailed(
            error instanceof Error
              ? error.message
              : "No se pudo cargar PayPal.",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [clientId, mode, planId, teamId]);

  return (
    <div className="space-y-1.5">
      <div
        ref={target}
        className={disabled ? "pointer-events-none opacity-50" : ""}
      />
      {loading && (
        <p className="inline-flex items-center gap-1.5 text-[10px] text-slate-400">
          <IconLoader size={12} className="animate-spin" />
          Cargando PayPal...
        </p>
      )}
      {failed && (
        <p className="flex items-start gap-1.5 text-[10px] leading-relaxed text-rose-600">
          <IconAlert size={12} className="mt-0.5 shrink-0" />
          {failed}
        </p>
      )}
      {!loading && !failed && (
        <p className="text-[9px] leading-relaxed text-slate-400">
          Plan {planName}. Se renueva cada mes; puedes cancelar cuando quieras.
        </p>
      )}
    </div>
  );
}
