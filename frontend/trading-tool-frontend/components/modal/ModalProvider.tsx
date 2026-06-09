"use client";

import {
  createContext,
  useContext,
  useEffect,
  useCallback,
  useState,
  ReactNode,
} from "react";
import { toast } from "react-hot-toast";
import { X, CheckCircle2, Info, AlertTriangle } from "lucide-react";
import { actionButtonStyles } from "@/components/ui/actionButtonStyles";

/* ===========================================================
   TYPES
=========================================================== */

type ModalTone = "primary" | "danger" | "info" | "success";
type ModalButtonVariant = "primary" | "danger";

export type ModalConfig = {
  title?: string;
  description?: ReactNode;
  statusLabel?: string;
  context?: ReactNode;
  impact?: ReactNode;
  safety?: ReactNode;
  consequence?: ReactNode;
  icon?: ReactNode;
  tone?: ModalTone;
  confirmText?: string;
  cancelText?: string;
  busyText?: string;
  onConfirm?: () => void | Promise<void>;
  onCancel?: () => void;
};

type SnackbarTone = "success" | "danger" | "info" | "primary";

export type ModalContextValue = {
  openConfirm: (config: ModalConfig) => void;
  close: () => void;
  showSnackbar: (msg: string, tone?: SnackbarTone) => void;
};

/* ===========================================================
   CONTEXT
=========================================================== */

const ModalContext = createContext<ModalContextValue | null>(null);

export function useModal(): ModalContextValue {
  const ctx = useContext(ModalContext);
  if (!ctx) {
    throw new Error("❌ useModal must be used within a ModalProvider");
  }
  return ctx;
}

/* ===========================================================
   PROVIDER
=========================================================== */

export function ModalProvider({ children }: { children: ReactNode }) {
  const [modal, setModal] = useState<ModalConfig | null>(null);
  const [busy, setBusy] = useState(false);

  /* --- CLOSE MODAL --- */
  const close = useCallback(() => {
    if (busy) return;
    modal?.onCancel?.();
    setModal(null);
  }, [modal, busy]);

  /* --- OPEN MODAL --- */
  const openConfirm = useCallback((config: ModalConfig) => {
    setBusy(false);
    setModal(config);
  }, []);

  /* --- SNACKBAR (UNIFIED WITH TOAST) --- */
  const showSnackbar = useCallback(
    (msg: string, tone: SnackbarTone = "success") => {
      const options = {
        id: msg, // Prevent duplicates
      };
      if (tone === "success") toast.success(msg, options);
      else if (tone === "danger") toast.error(msg, options);
      else toast(msg, options);
    },
    []
  );

  /* --- SCROLL LOCK + ESCAPE --- */
  useEffect(() => {
    if (!modal) return;

    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const esc = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", esc);

    return () => {
      document.body.style.overflow = prevOverflow;
      window.removeEventListener("keydown", esc);
    };
  }, [modal, close]);

  return (
    <ModalContext.Provider value={{ openConfirm, close, showSnackbar }}>
      {children}

      <ModalRoot modal={modal} busy={busy} setBusy={setBusy} onClose={close} />
    </ModalContext.Provider>
  );
}

/* ===========================================================
   MODAL ROOT — UI
=========================================================== */

function ModalRoot({
  modal,
  busy,
  setBusy,
  onClose,
}: {
  modal: ModalConfig | null;
  busy: boolean;
  setBusy: (v: boolean) => void;
  onClose: () => void;
}) {
  if (!modal) return null;

  const {
    title = "Bevestig actie",
    description,
    statusLabel,
    context,
    impact,
    safety,
    consequence,
    icon,
    tone = "primary",
    confirmText = "Bevestigen",
    cancelText = "Annuleren",
    busyText,
    onConfirm,
  } = modal;

  const toneClasses: {
    iconBg: string;
    iconText: string;
    confirmVariant: ModalButtonVariant;
  } =
    tone === "danger"
      ? {
          iconBg: "bg-red-100 dark:bg-red-900/40",
          iconText: "text-red-600 dark:text-red-400",
          confirmVariant: "danger",
        }
      : tone === "info"
      ? {
          iconBg: "bg-blue-100 dark:bg-blue-900/40",
          iconText: "text-blue-600 dark:text-blue-400",
          confirmVariant: "primary",
        }
      : tone === "success"
      ? {
          iconBg: "bg-green-100 dark:bg-green-900/40",
          iconText: "text-green-600 dark:text-green-400",
          confirmVariant: "primary",
        }
      : {
          iconBg: "bg-blue-100 dark:bg-blue-900/40",
          iconText: "text-blue-600 dark:text-blue-400",
          confirmVariant: "primary",
        };

  const handleConfirm = async () => {
    if (!onConfirm) {
      onClose();
      return;
    }

    try {
      setBusy(true);
      await onConfirm();
      onClose();
    } catch (err) {
      console.error("❌ Modal onConfirm error:", err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[210] bg-black/60 backdrop-blur-sm flex items-center justify-center px-4 animate-fade-in">
      <div className="w-full max-w-md bg-card dark:bg-[#0f172a] border border-slate-200 dark:border-slate-800 rounded-2xl shadow-xl animate-fade-slide flex flex-col max-h-[85vh] relative overflow-hidden transition-colors">

        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-2 rounded-xl text-secondary hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition-all z-10"
        >
          <X className="w-5 h-5" />
        </button>

        <div className="px-8 pt-8 pb-6 flex items-start gap-4">
          {icon && (
            <div className={`rounded-2xl p-3 ${toneClasses.iconBg}`}>
              <div className={toneClasses.iconText}>{icon}</div>
            </div>
          )}
          <div className="space-y-2">
            {statusLabel ? (
              <span className="inline-flex rounded-full border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 px-2.5 py-1 text-[10px] font-black uppercase tracking-[0.22em] text-slate-500 dark:text-slate-300">
                {statusLabel}
              </span>
            ) : null}
            <h2 className="text-2xl font-black text-foreground dark:text-white tracking-tight">{title}</h2>
          </div>
        </div>

        {(description || context || impact || safety || consequence) && (
          <div className="flex-1 overflow-y-auto px-8 py-2 space-y-4 text-[15px] font-medium text-muted dark:text-slate-400 leading-relaxed">
            {description ? <div>{description}</div> : null}
            {context ? <ModalSection label="Context">{context}</ModalSection> : null}
            {impact ? <ModalSection label="Impact">{impact}</ModalSection> : null}
            {safety ? <ModalSection label="Veiligheid">{safety}</ModalSection> : null}
            {consequence ? <ModalSection label="Daarna">{consequence}</ModalSection> : null}
          </div>
        )}

        <div className="px-8 py-8 flex justify-end gap-4 mt-4">
          <button
            onClick={onClose}
            disabled={busy}
            className={actionButtonStyles({ variant: "secondary" })}
          >
            {cancelText}
          </button>

          <button
            onClick={handleConfirm}
            disabled={busy}
            className={actionButtonStyles({
              variant: toneClasses.confirmVariant,
              className: "shadow-sm",
            })}
          >
            {busy && <div className="w-4 h-4 border-2 border-white/30 border-t-white animate-spin rounded-full" />}
            {busy ? busyText || "Bezig..." : confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}

function ModalSection({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-slate-100 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-900/50 px-4 py-3">
      <div className="mb-2 text-[10px] font-black uppercase tracking-[0.22em] text-slate-500 dark:text-slate-400">
        {label}
      </div>
      <div className="text-[14px] font-semibold text-slate-700 dark:text-slate-300 leading-relaxed">
        {children}
      </div>
    </div>
  );
}
