"use client";

import { useState } from "react";
import Link from "next/link";
import { Mail, ShieldCheck } from "lucide-react";

import { useModal } from "@/components/modal/ModalProvider";
import { useTranslation } from "@/app/providers/I18nProvider";
import { apiForgotPassword } from "@/lib/api/auth";

export default function ForgotPasswordPage() {
  const { showSnackbar } = useModal();
  const { t, locale } = useTranslation();
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (submitting) return;

    setSubmitting(true);
    const result = await apiForgotPassword(email, locale);

    if (!result.success) {
      showSnackbar(t?.auth?.resetRequestFailed || t?.auth?.serverUnreachable, "danger");
      setSubmitting(false);
      return;
    }

    setSubmitted(true);
    showSnackbar(t?.auth?.resetRequestSent, "success");
    setSubmitting(false);
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
            {t?.auth?.forgotPasswordTitle}
          </h1>
          <p className="page-subtitle mx-auto mt-4">
            {submitted ? t?.auth?.resetRequestSentDescription : t?.auth?.forgotPasswordDescription}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-8">
          <div className="space-y-3">
            <label className="metric-label ml-1">{t?.auth?.email}</label>
            <div className="relative group">
              <Mail size={18} className="absolute right-5 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-blue-600 transition-colors z-10" />
              <input
                type="email"
                required
                disabled={submitted}
                className="trade-input pr-14"
                placeholder={t?.auth?.emailPlaceholder}
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={submitting || submitted}
            className="btn-primary w-full flex items-center justify-center gap-3 py-5 text-[13px]"
          >
            {submitting ? t?.auth?.sendingReset : t?.auth?.sendResetLink}
          </button>
        </form>

        <div className="text-center mt-10 pt-8 border-t-2 border-slate-50">
          <Link href="/login" className="text-blue-600 font-bold hover:underline uppercase tracking-widest text-[10px]">
            {t?.auth?.backToLogin}
          </Link>
        </div>
      </div>
    </div>
  );
}
