"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Eye, EyeOff, Lock, ShieldCheck } from "lucide-react";

import { useModal } from "@/components/modal/ModalProvider";
import { useTranslation } from "@/app/providers/I18nProvider";
import { apiResetPassword, apiValidateResetPasswordToken } from "@/lib/api/auth";

function ResetPasswordContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { showSnackbar } = useModal();
  const { t } = useTranslation();
  const token = searchParams.get("token") || "";

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [validating, setValidating] = useState(true);
  const [tokenValid, setTokenValid] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [completed, setCompleted] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function validateToken() {
      if (!token) {
        if (!cancelled) {
          setTokenValid(false);
          setValidating(false);
        }
        return;
      }

      const result = await apiValidateResetPasswordToken(token);
      if (!cancelled) {
        setTokenValid(Boolean(result.valid));
        setValidating(false);
      }
    }

    void validateToken();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (submitting) return;

    if (password.length < 8) {
      showSnackbar(t?.auth?.passwordTooShort, "danger");
      return;
    }
    if (password !== confirmPassword) {
      showSnackbar(t?.auth?.passwordMismatch, "danger");
      return;
    }

    setSubmitting(true);
    const result = await apiResetPassword(token, password);
    if (!result.success) {
      showSnackbar(result.message || t?.auth?.resetPasswordFailed, "danger");
      setSubmitting(false);
      return;
    }

    setCompleted(true);
    showSnackbar(t?.auth?.resetPasswordSuccess, "success");
    setTimeout(() => {
      router.push("/login");
    }, 1200);
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--bg-premium-gradient)] px-4">
      <div className="w-full max-w-md card bg-white/95 backdrop-blur-sm p-10 animate-fade-in">
        <div className="text-center mb-10">
          <div className="flex items-center justify-center gap-4 mb-10 scale-110 group">
            <div className="relative">
              <img src="/tradamind_icon_v2.png" alt="TM" className="h-20 w-20 object-contain rounded-2xl transition-all duration-500" />
            </div>
            <div className="flex flex-col items-start justify-center text-left">
              <div className="text-3xl font-black text-slate-900 tracking-tight leading-none mb-1.5">
                Tradamind
              </div>
              <div className="flex items-center gap-1.5 text-blue-600 mb-2">
                <div className="animate-pulse-soft">
                  <ShieldCheck size={18} strokeWidth={2.5} />
                </div>
                <div className="text-[11px] font-black uppercase tracking-[0.3em]">
                  {t?.auth?.professional}
                </div>
              </div>
              <div className="text-[8px] font-bold text-slate-400 uppercase tracking-[0.25em] opacity-80 border-t border-slate-100 pt-2 w-full">
                {t?.auth?.taglineLine1}<br />{t?.auth?.taglineLine2}
              </div>
            </div>
          </div>

          <div className="page-label mb-3">{t?.auth?.resetEyebrow}</div>
          <h1 className="text-3xl font-bold text-foreground tracking-tighter text-center">
            {t?.auth?.resetPasswordTitle}
          </h1>
          <p className="page-subtitle mx-auto mt-4">
            {validating
              ? t?.auth?.validatingResetLink
              : tokenValid
                ? (completed ? t?.auth?.resetPasswordSuccess : t?.auth?.resetPasswordDescription)
                : t?.auth?.invalidResetLink}
          </p>
        </div>

        {validating ? (
          <div className="flex justify-center py-8">
            <div className="h-10 w-10 animate-spin rounded-full border-4 border-blue-600/30 border-t-blue-600" />
          </div>
        ) : tokenValid ? (
          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="space-y-3">
              <label className="metric-label ml-1">{t?.auth?.newPassword}</label>
              <div className="relative group">
                <button
                  type="button"
                  onClick={() => setShowPassword((value) => !value)}
                  className="absolute right-5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-blue-600 transition-colors z-20"
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
                <Lock size={18} className="absolute left-5 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-blue-600 transition-colors z-10" />
                <input
                  type={showPassword ? "text" : "password"}
                  required
                  minLength={8}
                  className="trade-input pl-14 pr-14"
                  placeholder="•••••••••"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
              </div>
            </div>

            <div className="space-y-3">
              <label className="metric-label ml-1">{t?.auth?.confirmPassword}</label>
              <div className="relative group">
                <Lock size={18} className="absolute left-5 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-blue-600 transition-colors z-10" />
                <input
                  type={showPassword ? "text" : "password"}
                  required
                  minLength={8}
                  className="trade-input pl-14 pr-14"
                  placeholder="•••••••••"
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={submitting || completed}
              className="btn-primary w-full flex items-center justify-center gap-3 py-5 text-[13px]"
            >
              {submitting ? t?.auth?.resettingPassword : t?.auth?.saveNewPassword}
            </button>
          </form>
        ) : (
          <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-4 text-sm font-semibold text-red-700">
            {t?.auth?.invalidResetLink}
          </div>
        )}

        <div className="text-center mt-10 pt-8 border-t-2 border-slate-50">
          <Link href="/login" className="text-blue-600 font-bold hover:underline uppercase tracking-widest text-[10px]">
            {t?.auth?.backToLogin}
          </Link>
        </div>
      </div>
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-[var(--bg-premium-gradient)]" />}>
      <ResetPasswordContent />
    </Suspense>
  );
}
