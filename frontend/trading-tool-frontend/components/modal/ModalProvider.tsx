"use client";

import {
  createContext,
  useContext,
  useEffect,
  useCallback,
  useState,
  ReactNode,
} from "react";

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
    throw new Error("❌ useModal moet binnen ModalProvider gebruikt worden");
  }
  return ctx;
}

/* ===========================================================
   PROVIDER
=========================================================== */

export function ModalProvider({ children }: { children: ReactNode }) {
  const [modal, setModal] = useState<ModalConfig | null>(null);
  const [busy, setBusy] = useState(false);

  // Snackbar state
  const [snackbar, setSnackbar] = useState<{
    msg: string;
    tone: SnackbarTone;
    visible: boolean;
  }>({ msg: "", tone: "success", visible: false });

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

  /* --- SNACKBAR --- */
  const showSnackbar = useCallback(
    (msg: string, tone: SnackbarTone = "success") => {
      setSnackbar({ msg, tone, visible: true });

      const timer = setTimeout(() => {
        setSnackbar((s) => ({ ...s, visible: false }));
      }, 2500);

      return () => clearTimeout(timer);
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
      <Snackbar snackbar={snackbar} />
    </ModalContext.Provider>
  );
}

/* ===========================================================
   MODAL ROOT — UI (SCROLL SAFE)
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
    title = "Bevestigen",
    description,
    icon,
    tone = "primary",
    confirmText = "Bevestigen",
    cancelText = "Annuleren",
    onConfirm,
  } = modal;

  const toneClasses =
    tone === "danger"
      ? {
          iconBg: "bg-red-100 dark:bg-red-900/40",
          iconText: "text-red-600",
          confirm: "bg-red-600 hover:bg-red-700",
        }
      : tone === "info"
      ? {
          iconBg: "bg-blue-100 dark:bg-blue-900/40",
          iconText: "text-blue-600",
          confirm: "bg-blue-600 hover:bg-blue-700",
        }
      : tone === "success"
      ? {
          iconBg: "bg-green-100 dark:bg-green-900/40",
          iconText: "text-green-600",
          confirm: "bg-green-600 hover:bg-green-700",
        }
      : {
          iconBg: "bg-[var(--primary-soft)]",
          iconText: "text-[var(--primary)]",
          confirm: "bg-[var(--primary)] hover:brightness-90",
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
    <div className="fixed inset-0 z-[210] bg-black/55 backdrop-blur-sm flex items-center justify-center px-4 animate-fade-in">
      <div className="w-full max-w-md bg-[var(--card-bg)] border border-[var(--card-border)] rounded-2xl shadow-2xl animate-fade-slide flex flex-col max-h-[85vh] relative">

        {/* Close */}
        <button
          onClick={onClose}
          className="absolute top-3 right-3 p-2 rounded-lg text-gray-500 hover:text-gray-800 dark:hover:text-gray-100 hover:bg-black/10 dark:hover:bg-white/10 transition"
        >
          <X className="w-4 h-4" />
        </button>

        {/* HEADER */}
        <div className="px-6 pt-6 pb-4 border-b flex items-center gap-3">
          {icon && (
            <div className={`rounded-full p-2 ${toneClasses.iconBg}`}>
              <div className={toneClasses.iconText}>{icon}</div>
            </div>
          )}
          <h2 className="text-xl font-semibold">{title}</h2>
        </div>

        {/* SCROLLABLE CONTENT */}
        {description && (
          <div className="flex-1 overflow-y-auto px-6 py-4 text-sm text-gray-700 dark:text-gray-200">
            {description}
          </div>
        )}

        {/* FOOTER (ALTIJD ZICHTBAAR) */}
        <div className="border-t px-6 py-4 flex justify-end gap-3 bg-[var(--card-bg)] sticky bottom-0">
          <button
            onClick={onClose}
            disabled={busy}
            className="px-4 py-2 rounded-xl text-sm border border-gray-300 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 hover:bg-gray-100 dark:hover:bg-gray-800 transition"
          >
            {cancelText}
          </button>

          <button
            onClick={handleConfirm}
            disabled={busy}
            className={`px-4 py-2 rounded-xl text-sm text-white shadow-md ${toneClasses.confirm}`}
          >
            {busy ? "Bezig…" : confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ===========================================================
   SNACKBAR — UI
=========================================================== */

function Snackbar({
  snackbar,
}: {
  snackbar: { msg: string; tone: SnackbarTone; visible: boolean };
}) {
  if (!snackbar.visible) return null;

  const toneStyles = {
    success: "bg-green-600",
    danger: "bg-red-600",
    info: "bg-blue-600",
    primary: "bg-[var(--primary)]",
  };

  const Icon =
    snackbar.tone === "danger"
      ? AlertTriangle
      : snackbar.tone === "info"
      ? Info
      : CheckCircle2;

  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-[220] animate-snackbar-fade">
      <div
        className={`
          px-5 py-3 rounded-full shadow-xl backdrop-blur-lg
          text-white flex items-center gap-2
          ${toneStyles[snackbar.tone]}
        `}
      >
        <Icon className="w-4 h-4" />
        <span className="font-medium text-sm">{snackbar.msg}</span>
      </div>
    </div>
  );
}
