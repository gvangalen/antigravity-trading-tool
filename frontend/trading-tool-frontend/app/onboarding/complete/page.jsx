"use client";

import { useEffect } from "react";
import { CheckCircle2, ArrowRight, LayoutDashboard, FileText, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTranslation } from "@/app/providers/I18nProvider";
import useBootstrapAgents from "@/hooks/useBootstrapAgents";
import { trackAssistantEvent } from "@/lib/api/assistantAnalytics";

export default function OnboardingCompletePage() {
  const router = useRouter();
  const { t } = useTranslation();
  const { runBootstrap, loading } = useBootstrapAgents();

  useEffect(() => {
    trackAssistantEvent({
      event_name: "screen_view",
      page: "/onboarding/complete",
      surface: "web",
      flow_type: "onboarding_complete",
    });
  }, []);

  const handleGoToDashboard = async () => {
    trackAssistantEvent({
      event_name: "onboarding_complete_continue_clicked",
      page: "/onboarding/complete",
      surface: "web",
      flow_type: "first_session",
      action_type: "go_to_dashboard",
    });

    try {
      await runBootstrap();
    } catch (err) {
      console.error("Bootstrap agents error:", err);
    } finally {
      router.push("/");
    }
  };

  return (
    <div className="mx-auto max-w-screen-md animate-fade-slide px-6 py-20 text-center">
      <div className="mb-6 flex justify-center">
        <CheckCircle2 size={70} className="text-green-500 drop-shadow-md" />
      </div>

      <h1 className="mb-4 text-4xl font-bold text-[var(--text-dark)]">
        {t?.traderProfile?.onboardingComplete?.title}
      </h1>

      <p className="mx-auto mb-10 max-w-xl text-lg leading-relaxed text-[var(--text-light)]">
        {t?.traderProfile?.onboardingComplete?.description}
      </p>

      <div className="mx-auto mb-10 max-w-2xl rounded-3xl border border-blue-100 bg-blue-50 p-6 text-left shadow-sm">
        <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.22em] text-blue-600">
          <Sparkles size={14} />
          {t?.traderProfile?.onboardingComplete?.finnLabel}
        </div>
        <p className="mt-3 text-sm font-semibold leading-relaxed text-slate-700">
          {t?.traderProfile?.onboardingComplete?.finnBody}
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <span className="inline-flex items-center gap-2 rounded-full border border-blue-200 bg-white px-3 py-1.5 text-xs font-bold text-blue-700">
            <LayoutDashboard size={12} />
            {t?.traderProfile?.onboardingComplete?.chips?.dashboard}
          </span>
          <span className="inline-flex items-center gap-2 rounded-full border border-blue-200 bg-white px-3 py-1.5 text-xs font-bold text-blue-700">
            <FileText size={12} />
            {t?.traderProfile?.onboardingComplete?.chips?.report}
          </span>
          <span className="inline-flex items-center gap-2 rounded-full border border-blue-200 bg-white px-3 py-1.5 text-xs font-bold text-blue-700">
            <Sparkles size={12} />
            {t?.traderProfile?.onboardingComplete?.chips?.askFinn}
          </span>
        </div>
      </div>

      <button
        onClick={handleGoToDashboard}
        disabled={loading}
        className="inline-flex items-center gap-2 rounded-xl bg-[var(--primary)] px-6 py-3 font-semibold text-white shadow-md transition hover:bg-[var(--primary-dark)] hover:shadow-lg disabled:opacity-60"
      >
        {loading
          ? t?.traderProfile?.onboardingComplete?.loading
          : t?.traderProfile?.onboardingComplete?.cta}
        <ArrowRight size={18} />
      </button>

      <p className="mt-6 text-sm text-[var(--text-light)]">
        {t?.traderProfile?.onboardingComplete?.footer}
      </p>
    </div>
  );
}
