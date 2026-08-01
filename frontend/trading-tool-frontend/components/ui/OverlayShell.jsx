"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  applyBodyScrollLock,
  createOverlayStack,
  getScrollbarCompensation,
  restoreBodyScrollLock,
} from "@/components/ui/overlayUtils";

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled]):not([type='hidden'])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
  "[contenteditable='true']",
].join(", ");

const overlayStack = createOverlayStack();
let listenerDocument = null;
let releaseBodyScrollLock = null;

function isElementVisible(element) {
  if (!element) return false;
  if (element.hasAttribute("hidden")) return false;
  if (element.getAttribute("aria-hidden") === "true") return false;
  if (typeof window === "undefined") return true;

  const style = window.getComputedStyle(element);
  if (style.display === "none" || style.visibility === "hidden") return false;
  return element.getClientRects().length > 0;
}

function getFocusableElements(container) {
  if (!container) return [];
  return Array.from(container.querySelectorAll(FOCUSABLE_SELECTOR)).filter((element) => {
    if (!(element instanceof HTMLElement)) return false;
    return isElementVisible(element);
  });
}

function focusFirstElement(container, initialFocusRef) {
  const preferred = initialFocusRef?.current;
  if (preferred instanceof HTMLElement && !preferred.hasAttribute("disabled")) {
    preferred.focus();
    return;
  }

  const autofocus = container?.querySelector("[data-autofocus='true'], [autofocus]");
  if (autofocus instanceof HTMLElement) {
    autofocus.focus();
    return;
  }

  const focusables = getFocusableElements(container);
  if (focusables[0]) {
    focusables[0].focus();
    return;
  }

  if (container instanceof HTMLElement) {
    container.focus();
  }
}

function trapFocus(event, container) {
  if (event.key !== "Tab") return;

  const focusables = getFocusableElements(container);
  if (!focusables.length) {
    event.preventDefault();
    container?.focus();
    return;
  }

  const first = focusables[0];
  const last = focusables[focusables.length - 1];
  const active = document.activeElement;

  if (!container?.contains(active)) {
    event.preventDefault();
    (event.shiftKey ? last : first).focus();
    return;
  }

  if (!event.shiftKey && active === last) {
    event.preventDefault();
    first.focus();
    return;
  }

  if (event.shiftKey && active === first) {
    event.preventDefault();
    last.focus();
  }
}

function syncGlobalListeners(doc) {
  if (listenerDocument === doc && overlayStack.size() > 0) return;

  if (listenerDocument && listenerDocument !== doc) {
    listenerDocument.removeEventListener("keydown", handleGlobalKeydown, true);
    listenerDocument = null;
  }

  if (!doc || overlayStack.size() === 0) return;

  doc.addEventListener("keydown", handleGlobalKeydown, true);
  listenerDocument = doc;
}

function handleGlobalKeydown(event) {
  const top = overlayStack.top();
  if (!top) return;

  if (event.key === "Escape") {
    top.onEscape?.(event);
    return;
  }

  if (event.key === "Tab") {
    top.onTab?.(event);
  }
}

function lockBodyScroll(doc) {
  if (releaseBodyScrollLock) return;

  const snapshot = applyBodyScrollLock(doc, getScrollbarCompensation(window, doc));
  releaseBodyScrollLock = () => {
    restoreBodyScrollLock(doc, snapshot);
    releaseBodyScrollLock = null;
  };
}

function unlockBodyScrollIfNeeded() {
  if (overlayStack.size() > 0) return;
  releaseBodyScrollLock?.();
}

function resolveBlockedState(value) {
  return typeof value === "function" ? Boolean(value()) : Boolean(value);
}

export default function OverlayShell({
  isOpen,
  onClose,
  variant = "dialog",
  labelledBy = undefined,
  describedBy = undefined,
  ariaLabel = undefined,
  initialFocusRef = undefined,
  closeOnBackdrop = true,
  closeOnEscape = true,
  isCloseBlocked = false,
  rootClassName = "",
  backdropClassName = "",
  positionClassName = "",
  panelClassName = "",
  children,
}) {
  const generatedLabelId = useId();
  const [mounted, setMounted] = useState(false);
  const panelRef = useRef(null);
  const openerRef = useRef(null);
  const overlayIdRef = useRef(`overlay-${generatedLabelId}`);
  const entryRef = useRef(null);

  const labelId = labelledBy || generatedLabelId;

  const requestClose = useCallback((reason) => {
    if (resolveBlockedState(isCloseBlocked)) return;
    onClose?.(reason);
  }, [isCloseBlocked, onClose]);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!isOpen || typeof document === "undefined") return;

    openerRef.current = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;

    const entry = {
      id: overlayIdRef.current,
      onEscape: (event) => {
        if (!closeOnEscape || resolveBlockedState(isCloseBlocked)) return;
        event.preventDefault();
        event.stopPropagation();
        requestClose("escape");
      },
      onTab: (event) => {
        if (resolveBlockedState(isCloseBlocked) && event.key !== "Tab") return;
        trapFocus(event, panelRef.current);
      },
    };

    entryRef.current = entry;
    overlayStack.add(entry);
    syncGlobalListeners(document);
    lockBodyScroll(document);

    return () => {
      overlayStack.remove(overlayIdRef.current);
      syncGlobalListeners(document);
      if (overlayStack.size() === 0 && listenerDocument) {
        listenerDocument.removeEventListener("keydown", handleGlobalKeydown, true);
        listenerDocument = null;
      }
      unlockBodyScrollIfNeeded();

      const opener = openerRef.current;
      if (opener instanceof HTMLElement && document.contains(opener)) {
        opener.focus();
      }
    };
  }, [closeOnEscape, isCloseBlocked, isOpen, requestClose]);

  useEffect(() => {
    if (!isOpen || !mounted) return;

    const handle = window.requestAnimationFrame(() => {
      focusFirstElement(panelRef.current, initialFocusRef);
    });

    return () => window.cancelAnimationFrame(handle);
  }, [initialFocusRef, isOpen, mounted]);

  if (!isOpen || !mounted || typeof document === "undefined") return null;

  return createPortal(
    <div className={`fixed inset-0 overflow-hidden ${rootClassName}`.trim()}>
      <div
        aria-hidden="true"
        className={`absolute inset-0 ${backdropClassName}`.trim()}
        onClick={closeOnBackdrop ? () => requestClose("backdrop") : undefined}
      />
      <div className={positionClassName}>
        <div
          ref={panelRef}
          role="dialog"
          aria-modal="true"
          aria-labelledby={ariaLabel ? undefined : labelId}
          aria-describedby={describedBy}
          aria-label={ariaLabel}
          data-overlay-variant={variant}
          tabIndex={-1}
          className={panelClassName}
          onClick={(event) => event.stopPropagation()}
        >
          {children}
        </div>
      </div>
    </div>,
    document.body
  );
}
