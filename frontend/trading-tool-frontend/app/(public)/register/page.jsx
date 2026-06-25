"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Mail, Lock, UserPlus, User, ShieldCheck } from "lucide-react";

import { API_BASE_URL } from "@/lib/config";
import { useAuth } from "@/components/auth/AuthProvider";
import { useModal } from "@/components/modal/ModalProvider";
import { useTranslation } from "@/app/providers/I18nProvider";

export default function RegisterPage() {
  const router = useRouter();
  const { login, isAuthenticated, sessionChecked } = useAuth();
  const { showSnackbar } = useModal();
  const { t } = useTranslation();

  const [name, setName] = useState(""); 
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  // voorkomt dubbele redirects zoals bij login
  const redirected = useRef(false);

  // 🚀 Als user al ingelogd is EN de sessie is geverifieerd door backend → direct naar dashboard
  useEffect(() => {
    if (sessionChecked && isAuthenticated && !redirected.current) {
      redirected.current = true;
      router.replace("/dashboard");
    }
  }, [isAuthenticated, sessionChecked, router]);

  const handleRegister = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      // 1️⃣ Account aanmaken
      const res = await fetch(`${API_BASE_URL}/api/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          first_name: name,
          email,
          password
        }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        showSnackbar(
          data.detail || t?.auth?.registerFailed,
          "danger"
        );
        setLoading(false);
        return;
      }

      showSnackbar(t?.auth?.registerSuccess, "success");

      // 2️⃣ Automatisch inloggen
      const loginRes = await login(email, password);

      if (!loginRes.success) {
        showSnackbar(t?.auth?.registerManualLogin, "info");
        router.replace("/login");
        return;
      }

      // 3️⃣ Naar dashboard
      router.replace("/dashboard");
    } catch (err) {
      console.error("❌ Register fout:", err);
      showSnackbar(
        typeof navigator !== "undefined" && !navigator.onLine
          ? t?.auth?.offline
          : t?.auth?.serverUnreachable,
        "danger"
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--bg-premium-gradient)] px-4">
      <div className="w-full max-w-md card bg-white/95 backdrop-blur-sm p-10 animate-fade-in">

        <div className="text-center mb-10">
          <div className="flex items-center justify-center gap-4 mb-10 scale-110 group">
            <div className="relative">
              <img 
                src="/tradamind_icon_v2.png" 
                alt="TM" 
                className="h-20 w-20 object-contain rounded-2xl transition-all duration-500" 
              />
            </div>
            <div className="flex flex-col items-start justify-center text-left">
              <div className="text-3xl font-black text-slate-900 dark:text-white tracking-tight leading-none mb-1.5 transition-colors duration-300 group-hover:text-blue-600 dark:group-hover:text-blue-400">
                Tradamind
              </div>
              <div className="flex items-center gap-1.5 text-blue-600 dark:text-blue-500 mb-2">
                <div className="animate-pulse-soft">
                  <ShieldCheck size={18} strokeWidth={2.5} />
                </div>
                <div className="text-[11px] font-black uppercase tracking-[0.3em]">
                  Professional
                </div>
              </div>
              <div className="text-[8px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-[0.25em] opacity-80 border-t border-slate-100 dark:border-slate-800 pt-2 w-full">
                Trade Smarter. Follow your plan.<br/>Win consistently.
              </div>
            </div>
          </div>
          <div className="page-label mb-3">{t?.auth?.brandEyebrow}</div>
          <h1 className="text-3xl font-bold text-foreground dark:text-slate-100 tracking-tighter text-center">
            {t?.auth?.brandTitle}
          </h1>
          <p className="page-subtitle mx-auto mt-4">
            {t?.auth?.brandRegisterDescription}
          </p>
        </div>

        <form onSubmit={handleRegister} className="space-y-6">

          {/* Naam */}
          <div className="space-y-3">
            <label className="metric-label ml-1">
              {t?.auth?.fullName}
            </label>
            <div className="relative group">
              <User 
                size={18} 
                className="absolute right-5 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-blue-600 transition-colors z-10" 
              />
              <input
                type="text"
                required
                className="trade-input pr-14"
                placeholder={t?.auth?.fullNamePlaceholder}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
          </div>

          {/* E-mail */}
          <div className="space-y-3">
            <label className="metric-label ml-1">
              {t?.auth?.email}
            </label>
            <div className="relative group">
              <Mail 
                size={18} 
                className="absolute right-5 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-blue-600 transition-colors z-10" 
              />
              <input
                type="email"
                required
                className="trade-input pr-14"
                placeholder={t?.auth?.emailPlaceholder}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
          </div>

          {/* Wachtwoord */}
          <div className="space-y-3">
            <label className="metric-label ml-1">
              {t?.auth?.password}
            </label>
            <div className="relative group">
              <Lock 
                size={18} 
                className="absolute right-5 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-blue-600 transition-colors z-10" 
              />
              <input
                type="password"
                required
                minLength={6}
                className="trade-input pr-14"
                placeholder="•••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
          </div>

          {/* Submit */}
          <button
            type="submit"
            disabled={loading}
            className="btn-primary w-full flex items-center justify-center gap-3 py-5 text-[13px] mt-4"
          >
            {loading ? (
              <>{t?.auth?.creatingAccount}</>
            ) : (
              <>
                <UserPlus size={18} />
                {t?.auth?.createAccount?.toUpperCase?.() || t?.auth?.createAccount}
              </>
            )}
          </button>
        </form>

        <div className="text-center mt-10 pt-8 border-t-2 border-slate-50">
          <p className="metric-label text-slate-400 mb-0 lowercase normal-case tracking-normal">
            {t?.auth?.alreadyHaveAccount}
            <Link
              href="/login"
              className="text-blue-600 font-bold hover:underline ml-2 uppercase tracking-widest text-[10px]"
            >
              {t?.auth?.signInLink}
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
