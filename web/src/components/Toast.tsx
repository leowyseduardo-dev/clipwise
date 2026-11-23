import { IconAlert, IconCheck, IconSparkles, IconX } from "./icons";

export type ToastKind = "error" | "success" | "info";

export interface ToastState {
  id: number;
  message: string;
  kind: ToastKind;
}

const TONES: Record<ToastKind, string> = {
  error: "border-rose-200 bg-rose-50/95 text-rose-800",
  success: "border-emerald-200 bg-emerald-50/95 text-emerald-800",
  info: "border-slate-200 bg-white/95 text-slate-700",
};

export function Toast({
  toast,
  onClose,
}: {
  toast: ToastState;
  onClose: () => void;
}) {
  const Icon = toast.kind === "error" ? IconAlert : toast.kind === "success" ? IconCheck : IconSparkles;
  return (
    <div className="fixed bottom-5 left-1/2 z-[70] w-[calc(100%-2rem)] max-w-md -translate-x-1/2 sm:left-auto sm:right-6 sm:translate-x-0">
      <div
        role="status"
        aria-live="polite"
        className={`flex items-start gap-3 rounded-2xl border px-4 py-3 text-sm shadow-2xl backdrop-blur-xl ${TONES[toast.kind]}`}
      >
        <Icon size={18} className="mt-0.5 shrink-0" />
        <p className="flex-1 leading-snug">{toast.message}</p>
        <button
          type="button"
          onClick={onClose}
          className="rounded-lg p-1 opacity-70 transition hover:opacity-100"
          aria-label="Cerrar aviso"
        >
          <IconX size={16} />
        </button>
      </div>
    </div>
  );
}
