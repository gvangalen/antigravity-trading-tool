"use client";

import {
  createContext,
  useContext,
  useCallback,
  useState,
  useId,
  ReactNode,
} from "react";
import { toast } from "react-hot-toast";
import { X } from "lucide-react";
import { actionButtonStyles } from "@/components/ui/actionButtonStyles";
import OverlayShell from "@/components/ui/OverlayShell";

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
  closeOnBackdrop?: boolean;
  onConfirm?: () => void | boolean | Promise<void | boolean>;
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
  const titleId = useId();
  const descriptionId = useId();

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
      const shouldClose = await onConfirm();
      if (shouldClose !== false) {
        onClose();
      }
    } catch (err) {
      console.error("❌ Modal onConfirm error:", err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <OverlayShell
      isOpen={Boolean(modal)}
      onClose={onClose}
      variant="dialog"
      labelledBy={titleId}
      describedBy={description || context || impact || safety || consequence ? descriptionId : undefined}
      closeOnBackdrop={modal.closeOnBackdrop ?? true}
      closeOnEscape
      isCloseBlocked={busy}
      rootClassName="z-[210]"
      backdropClassName="bg-black/60 backdrop-blur-sm"
      positionClassName="fixed inset-0 flex items-center justify-center px-4"
      panelClassName="relative flex max-h-[85vh] w-full max-w-md flex-col overflow-hidden rounded-2xl border border-slate-200 bg-card shadow-xl transition-colors animate-fade-slide dark:border-slate-800 dark:bg-[#0f172a]"
    >
      <button
        onClick={() => onClose()}
        disabled={busy}
        aria-label="Sluiten"
        data-overlay-close="true"
        className="absolute right-4 top-4 z-10 rounded-xl p-2 text-secondary transition-all hover:bg-slate-100 hover:text-slate-900 dark:hover:bg-slate-800 dark:hover:text-white"
      >
        <X className="h-5 w-5" aria-hidden="true" />
      </button>

      <div className="flex items-start gap-4 px-8 pb-6 pt-8">
        {icon ? (
          <div className={`rounded-2xl p-3 ${toneClasses.iconBg}`} aria-hidden="true">
            <div className={toneClasses.iconText}>{icon}</div>
          </div>
        ) : null}
        <div className="space-y-2">
          {statusLabel ? (
            <span className="inline-flex rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[10px] font-black uppercase tracking-[0.22em] text-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300">
              {statusLabel}
            </span>
          ) : null}
          <h2 id={titleId} className="text-2xl font-black tracking-tight text-foreground dark:text-white">
            {title}
          </h2>
        </div>
      </div>

      {(description || context || impact || safety || consequence) && (
        <div
          id={descriptionId}
          className="flex-1 space-y-4 overflow-y-auto px-8 py-2 text-[15px] font-medium leading-relaxed text-muted dark:text-slate-400"
        >
          {description ? <div>{description}</div> : null}
          {context ? <ModalSection label="Context">{context}</ModalSection> : null}
          {impact ? <ModalSection label="Impact">{impact}</ModalSection> : null}
          {safety ? <ModalSection label="Veiligheid">{safety}</ModalSection> : null}
          {consequence ? <ModalSection label="Daarna">{consequence}</ModalSection> : null}
        </div>
      )}

      <div className="mt-4 flex justify-end gap-4 px-8 py-8">
        <button
          onClick={() => onClose()}
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
          {busy && <div className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />}
          {busy ? busyText || "Bezig..." : confirmText}
        </button>
      </div>
    </OverlayShell>
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
