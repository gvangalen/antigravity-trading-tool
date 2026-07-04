"use client";

import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Share, PlusSquare, Download, CheckCircle2, Smartphone } from "lucide-react";
import { useTranslation } from "@/app/providers/I18nProvider";

const DISMISS_KEY = "pwa-prompt-dismissed";
const SESSION_DISMISS_KEY = "pwa-prompt-dismissed-session";
const INSTALL_KEY = "pwa-installed";
const DISMISS_WINDOW_MS = 14 * 24 * 60 * 60 * 1000;
const COOKIE_DOMAIN = ".tradamind.com";

function getCookieOptions() {
  if (typeof window === "undefined") {
    return "path=/; max-age=31536000; samesite=lax";
  }

  const hostname = window.location.hostname;
  const sharedDomain =
    hostname === "tradamind.com" || hostname.endsWith(".tradamind.com")
      ? `; domain=${COOKIE_DOMAIN}`
      : "";

  return `path=/; max-age=31536000; samesite=lax${sharedDomain}`;
}

function readCookie(name) {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]+)`));
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

function writeCookie(name, value) {
  if (typeof document === "undefined") return;
  document.cookie = `${name}=${encodeURIComponent(value)}; ${getCookieOptions()}`;
}

function safeSessionGet(key) {
  try {
    return window.sessionStorage.getItem(key);
  } catch (error) {
    return null;
  }
}

function safeSessionSet(key, value) {
  try {
    window.sessionStorage.setItem(key, value);
  } catch (error) {}
}

function safeLocalGet(key) {
  try {
    return window.localStorage.getItem(key);
  } catch (error) {
    return null;
  }
}

function safeLocalSet(key, value) {
  try {
    window.localStorage.setItem(key, value);
  } catch (error) {}
}

function hasActiveDismissal() {
  if (typeof window === "undefined") return false;

  if (safeSessionGet(SESSION_DISMISS_KEY) === "1") {
    return true;
  }

  const lastDismissed = safeLocalGet(DISMISS_KEY) || readCookie(DISMISS_KEY);
  if (!lastDismissed) return false;

  const timestamp = Number.parseInt(lastDismissed, 10);
  if (!Number.isFinite(timestamp)) return false;

  return Date.now() - timestamp < DISMISS_WINDOW_MS;
}

export default function InstallPWA() {
  const { t } = useTranslation();
  const copy = t?.ui?.pwaPrompt || {};
  const [show, setShow] = useState(false);
  const [platform, setPlatform] = useState(null);
  const [deferredPrompt, setDeferredPrompt] = useState(null);
  const dismissedRef = useRef(false);

  useEffect(() => {
    // 1. Check if already installed
    const isStandalone = window.matchMedia("(display-mode: standalone)").matches 
      || (window.navigator).standalone 
      || document.referrer.includes("android-app://");

    if (isStandalone) return;

    if (safeLocalGet(INSTALL_KEY) === "1" || readCookie(INSTALL_KEY) === "1") return;

    // 2. Check dismissal
    dismissedRef.current = hasActiveDismissal();
    if (dismissedRef.current) {
      return;
    }

    // 3. Detect Platform
    const ua = window.navigator.userAgent.toLowerCase();
    const isiOS = /iphone|ipad|ipod/.test(ua);
    const isAndroid = /android/.test(ua);

    if (isiOS) setPlatform("ios");
    else if (isAndroid) setPlatform("android");
    else setPlatform("other");

    // 4. Handle Android Install Prompt
    const handler = (e) => {
      e.preventDefault();
      setDeferredPrompt(e);
      if (dismissedRef.current) return;
      window.setTimeout(() => {
        if (!dismissedRef.current) {
          setShow(true);
        }
      }, 3000);
    };

    const handleInstalled = () => {
      safeLocalSet(INSTALL_KEY, "1");
      writeCookie(INSTALL_KEY, "1");
      setShow(false);
      setDeferredPrompt(null);
    };

    window.addEventListener("beforeinstallprompt", handler);
    window.addEventListener("appinstalled", handleInstalled);

    // 5. iOS manually trigger show (since there's no native prompt)
    let iosTimer = null;
    if (isiOS) {
      iosTimer = window.setTimeout(() => {
        if (!dismissedRef.current) {
          setShow(true);
        }
      }, 5000);
    }

    return () => {
      if (iosTimer) {
        window.clearTimeout(iosTimer);
      }
      window.removeEventListener("beforeinstallprompt", handler);
      window.removeEventListener("appinstalled", handleInstalled);
    };
  }, []);

  const handleDismiss = () => {
    dismissedRef.current = true;
    setShow(false);
    if (typeof window !== "undefined") {
      const dismissedAt = Date.now().toString();
      safeLocalSet(DISMISS_KEY, dismissedAt);
      safeSessionSet(SESSION_DISMISS_KEY, "1");
      writeCookie(DISMISS_KEY, dismissedAt);
    }
  };

  const handleInstallAndroid = async () => {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    const { outcome } = await deferredPrompt.userChoice;
    if (outcome === "accepted") {
      if (typeof window !== "undefined") {
        safeLocalSet(INSTALL_KEY, "1");
        writeCookie(INSTALL_KEY, "1");
      }
      setShow(false);
    } else {
      handleDismiss();
    }
    setDeferredPrompt(null);
  };

  if (!show || !platform) return null;

  return (
    <AnimatePresence>
      <div className="fixed inset-x-0 bottom-0 z-[200] p-4 pb-10 md:pb-8 flex justify-center pointer-events-none">
        <motion.div
          initial={{ y: 100, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 100, opacity: 0 }}
          className="w-full max-w-sm bg-white dark:bg-[#0f172a] border-2 border-slate-100 dark:border-slate-800 rounded-[2.5rem] shadow-2xl pointer-events-auto overflow-hidden transition-colors"
        >
          <div className="p-8 space-y-6">
            {/* HEADER */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="w-14 h-14 bg-blue-600 rounded-2xl flex items-center justify-center text-white shadow-lg shadow-blue-600/20">
                  <Smartphone size={28} strokeWidth={2.5} />
                </div>
                <div>
                  <h3 className="text-xl font-black text-slate-900 dark:text-white tracking-tight leading-none mb-1.5 uppercase">
                    {copy.title}
                  </h3>
                  <div className="text-[10px] font-black text-blue-600 dark:text-blue-500 uppercase tracking-widest opacity-80 flex items-center gap-1.5">
                    <CheckCircle2 size={12} />
                    {copy.badge}
                  </div>
                </div>
              </div>
              <button 
                onClick={handleDismiss}
                className="p-2 rounded-xl text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-50 dark:hover:bg-slate-900 transition-all"
              >
                <X size={20} />
              </button>
            </div>

            {/* CONTENT */}
            <div className="space-y-4">
              <p className="text-[14px] font-bold text-slate-500 dark:text-slate-400 leading-relaxed">
                {copy.description}
              </p>

              {platform === "ios" ? (
                <div className="bg-slate-50 dark:bg-slate-900/50 rounded-2xl p-5 border border-slate-100 dark:border-slate-800/50 space-y-4">
                  <div className="flex items-start gap-4">
                    <div className="w-8 h-8 rounded-lg bg-white dark:bg-slate-800 flex items-center justify-center text-blue-600 shadow-sm shrink-0 mt-0.5">
                      <Share size={16} />
                    </div>
                    <div className="text-[13px] font-bold text-slate-700 dark:text-slate-300">
                      {copy.iosStep1Prefix} <span className="text-blue-600 dark:text-blue-500">{copy.iosShareLabel}</span> {copy.iosStep1Suffix}
                    </div>
                  </div>
                  <div className="flex items-start gap-4">
                    <div className="w-8 h-8 rounded-lg bg-white dark:bg-slate-800 flex items-center justify-center text-blue-600 shadow-sm shrink-0 mt-0.5">
                      <PlusSquare size={16} />
                    </div>
                    <div className="text-[13px] font-bold text-slate-700 dark:text-slate-300">
                      {copy.iosStep2Prefix} <span className="text-blue-600 dark:text-blue-500">{copy.iosAddToHomeLabel}</span>.
                    </div>
                  </div>
                </div>
              ) : (
                <button
                  onClick={handleInstallAndroid}
                  className="w-full py-4 bg-foreground text-white dark:bg-white dark:text-slate-900 rounded-2xl text-[12px] font-black uppercase tracking-[0.2em] transition-all flex items-center justify-center gap-3 shadow-xl active:scale-95"
                >
                  <Download size={18} strokeWidth={3} />
                  {copy.installNow}
                </button>
              )}
            </div>

            {/* FOOTER */}
            <button 
              onClick={handleDismiss}
              className="w-full text-center text-[10px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
            >
              {copy.later}
            </button>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
}
