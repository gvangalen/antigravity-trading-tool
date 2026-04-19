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

/* ===========================================================
   TYPES
=========================================================== */

type ModalTone = "primary" | "danger" | "info" | "success";

export type ModalConfig = {
  title?: string;
  description?: ReactNode;
  icon?: ReactNode;
  tone?: ModalTone;
  confirmText?: string;
  cancelText?: string;
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
    title = "Confirm",
    description,
    icon,
    tone = "primary",
    confirmText = "Confirm",
    cancelText = "Cancel",
    onConfirm,
  } = modal;

  const toneClasses =
    tone === "danger"
      ? {
          iconBg: "bg-red-100 dark:bg-red-900/40",
          iconText: "text-red-600 dark:text-red-400",
          confirm: "bg-red-600 hover:bg-red-700 shadow-red-600/20",
        }
      : tone === "info"
      ? {
          iconBg: "bg-blue-100 dark:bg-blue-900/40",
          iconText: "text-blue-600 dark:text-blue-400",
          confirm: "bg-blue-600 hover:bg-blue-700 shadow-blue-600/20",
        }
      : tone === "success"
      ? {
          iconBg: "bg-green-100 dark:bg-green-900/40",
          iconText: "text-green-600 dark:text-green-400",
          confirm: "bg-green-600 hover:bg-green-700 shadow-green-600/20",
        }
      : {
          iconBg: "bg-blue-100 dark:bg-blue-900/40",
          iconText: "text-blue-600 dark:text-blue-400",
          confirm: "bg-blue-600 hover:bg-blue-700 shadow-blue-600/20",
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
      <div className="w-full max-w-md bg-card dark:bg-[#0f172a] border-2 border-slate-100 dark:border-slate-800 rounded-3xl shadow-2xl animate-fade-slide flex flex-col max-h-[85vh] relative overflow-hidden transition-colors">

        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-2 rounded-xl text-secondary hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition-all z-10"
        >
          <X className="w-5 h-5" />
        </button>

        <div className="px-8 pt-8 pb-6 flex items-center gap-4">
          {icon && (
            <div className={`rounded-2xl p-3 ${toneClasses.iconBg}`}>
              <div className={toneClasses.iconText}>{icon}</div>
            </div>
          )}
          <h2 className="text-2xl font-black text-foreground dark:text-white tracking-tight">{title}</h2>
        </div>

        {description && (
          <div className="flex-1 overflow-y-auto px-8 py-2 text-[15px] font-medium text-muted dark:text-slate-400 leading-relaxed">
            {description}
          </div>
        )}

        <div className="px-8 py-8 flex justify-end gap-4 mt-4">
          <button
            onClick={onClose}
            disabled={busy}
            className="px-6 py-3 rounded-xl text-[12px] font-black uppercase tracking-widest border border-slate-200 dark:border-slate-800 bg-card dark:bg-slate-900 text-muted dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800 transition-all active:scale-95 disabled:opacity-50"
          >
            {cancelText}
          </button>

          <button
            onClick={handleConfirm}
            disabled={busy}
            className={`px-6 py-3 rounded-xl text-[12px] font-black uppercase tracking-widest text-white shadow-lg transition-all active:scale-95 disabled:opacity-50 flex items-center gap-2 ${toneClasses.confirm}`}
          >
            {busy && <div className="w-4 h-4 border-2 border-white/30 border-t-white animate-spin rounded-full" />}
            {busy ? "Processing…" : confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}
