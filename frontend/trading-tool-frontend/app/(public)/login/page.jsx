"use client";

import { Suspense, useState, useEffect, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/components/auth/AuthProvider";
import { Mail, Lock, LogIn, ShieldCheck, Eye, EyeOff } from "lucide-react";
import { useModal } from "@/components/modal/ModalProvider";
import { useTranslation } from "@/app/providers/I18nProvider";
import Link from "next/link";
import { getOnboardingStatus } from "@/lib/api/onboarding";

async function resolvePostLoginDestination(nextPath) {
  try {
    const status = await getOnboardingStatus();
    const isComplete = status?.onboarding_complete ?? (
      status?.has_profile &&
      status?.has_setup &&
      status?.has_technical &&
      status?.has_macro &&
      status?.has_market &&
      status?.has_strategy
    );
    if (!isComplete) return "/onboarding";
  } catch (error) {
    console.warn("⚠️ Could not resolve onboarding status after login:", error);
  }

  if (!nextPath || nextPath.startsWith("/login") || nextPath.startsWith("/register")) {
    return "/asset";
  }
  return nextPath;
}

function LoginPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { login, isAuthenticated, sessionChecked } = useAuth();
  const { showSnackbar } = useModal();
  const { t, locale } = useTranslation();
  const nextPath = searchParams.get("next") || "/asset";
  const reason = searchParams.get("reason");

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // voorkomt dubbele redirects
  const redirected = useRef(false);

  /* -------------------------------------------------------
     🚀 Als al ingelogd EN geverifieerd → dashboard
  ------------------------------------------------------- */
  useEffect(() => {
    if (!sessionChecked || !isAuthenticated || redirected.current) return;
    redirected.current = true;
    void resolvePostLoginDestination(nextPath).then((destination) => {
      router.push(destination);
    });
  }, [isAuthenticated, sessionChecked, nextPath, router]);

  /* -------------------------------------------------------
     LOGIN HANDLER
  ------------------------------------------------------- */
  const handleLogin = async (e) => {
    e.preventDefault();

    if (submitting) return;

    setSubmitting(true);

    const res = await login(email, password, locale);

    if (!res.success) {
      showSnackbar(res.message || t?.auth?.loginFailed, "danger");
      setSubmitting(false);
      return;
    }

    showSnackbar(t?.auth?.welcomeBack, "success");
    const destination = await resolvePostLoginDestination(nextPath);
    router.push(destination);
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--bg-premium-gradient)] px-4">
      <div className="w-full max-w-md card bg-white/95 backdrop-blur-sm p-10 animate-fade-in">

        {/* Titel */}
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
                  {t?.auth?.professional}
                </div>
              </div>
              <div className="text-[8px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-[0.25em] opacity-80 border-t border-slate-100 dark:border-slate-800 pt-2 w-full">
                {t?.auth?.taglineLine1}<br/>{t?.auth?.taglineLine2}
              </div>
            </div>
          </div>
          <div className="page-label mb-3">{t?.auth?.brandEyebrow}</div>
          <h1 className="text-3xl font-bold text-foreground dark:text-slate-100 tracking-tighter text-center">
            {t?.auth?.brandTitle}
          </h1>
          <p className="page-subtitle mx-auto mt-4">
            {t?.auth?.brandLoginDescription}
          </p>
          {reason === "session_expired" ? (
            <p className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-800">
              {t?.auth?.sessionExpired}
            </p>
          ) : null}
        </div>

        {/* Form */}
        <form onSubmit={handleLogin} className="space-y-8">

          {/* Email */}
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

          {/* Password */}
          <div className="space-y-3">
            <label className="metric-label ml-1">
              {t?.auth?.password}
            </label>
            <div className="relative group">
              <button 
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-blue-600 transition-colors z-20"
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
              <input
                type={showPassword ? "text" : "password"}
                required
                className="trade-input pr-14"
                placeholder="•••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
          </div>

          {/* Login button */}
          <button
            type="submit"
            disabled={submitting}
            className="btn-primary w-full flex items-center justify-center gap-3 py-5 text-[13px]"
          >
            {submitting ? (
              <>{t?.auth?.signingIn}</>
            ) : (
              <>
                <LogIn size={18} />
                {t?.auth?.signIn?.toUpperCase?.() || t?.auth?.signIn}
              </>
            )}
          </button>
        </form>

        {/* Registratie link */}
        <div className="text-center mt-10 pt-8 border-t-2 border-slate-50">
          <p className="metric-label text-slate-400 mb-0 lowercase normal-case tracking-normal">
            {t?.auth?.noAccount}
            <Link
              href="/register"
              className="text-blue-600 font-bold hover:underline ml-2 uppercase tracking-widest text-[10px]"
            >
              {t?.auth?.createOne}
            </Link>
          </p>
          <p className="mt-4 text-sm font-semibold text-slate-500">
            <Link href="/forgot-password" className="text-blue-600 hover:underline">
              {t?.auth?.forgotPassword}
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-[var(--bg-premium-gradient)]" />}>
      <LoginPageContent />
    </Suspense>
  );
}
