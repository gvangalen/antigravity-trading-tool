"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ClipboardList, PlusCircle, Search, Settings } from "lucide-react";

import SetupForm from "@/components/setup/SetupForm";
import SetupList from "@/components/setup/SetupList";
import SetupMatchCard from "@/components/setup/SetupMatchCard";
import AgentInsightPanel from "@/components/agents/AgentInsightPanel";
import OnboardingBanner from "@/components/onboarding/OnboardingBanner";
import OnboardingStepGuide from "@/components/onboarding/OnboardingStepGuide";
import DashboardErrorBoundary from "@/components/ui/DashboardErrorBoundary";
import { useSetupData } from "@/hooks/useSetupData";
import { useOnboarding } from "@/hooks/useOnboarding";
import { trackAssistantEvent } from "@/lib/api/assistantAnalytics";
import { useTranslation } from "@/app/providers/I18nProvider";

export default function SetupsWorkspaceSection() {
  const [search, setSearch] = useState("");
  const router = useRouter();
  const searchParams = useSearchParams();
  const { t } = useTranslation();
  const copy = t?.setupPage || {};
  const setupGuideCopy = copy.onboardingGuide || {};
  const { status, completeStep } = useOnboarding();
  const { setups, loading, error, loadSetups, saveSetup, removeSetup } = useSetupData();

  useEffect(() => {
    loadSetups();
  }, [loadSetups]);

  useEffect(() => {
    trackAssistantEvent({
      event_name: "screen_view",
      page: "/setup",
      surface: "web",
      flow_type: "setup",
    });
  }, []);

  useEffect(() => {
    if (Array.isArray(setups) && setups.length > 0 && status && status.has_setup === false) {
      completeStep("setup");
    }
  }, [setups, status, completeStep]);

  useEffect(() => {
    if (!status || status.has_asset) return;
    router.replace("/onboarding/asset?onboarding=1&step=asset");
  }, [status, router]);

  const reloadSetups = async () => {
    await loadSetups();
  };

  const safeSetups = Array.isArray(setups) ? setups : [];
  const setupStepComplete = Boolean(status?.has_setup || safeSetups.length > 0);
  const setupNeedsSetup = status?.has_setup === false && safeSetups.length === 0;
  const onboardingGuidedMode = searchParams.get("onboarding") === "1";
  const showOnboardingGuide = onboardingGuidedMode || setupNeedsSetup;

  return (
    <div className="space-y-8">
      <OnboardingBanner step="setup" />

      {showOnboardingGuide ? (
        <OnboardingStepGuide
          copy={setupGuideCopy}
          anchorId="setup-new"
          guidedMode={onboardingGuidedMode}
          isComplete={setupStepComplete}
          nextHref="/strategy?onboarding=1&step=strategy"
        />
      ) : null}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <DashboardErrorBoundary>
          <AgentInsightPanel category="setup" />
        </DashboardErrorBoundary>
        <DashboardErrorBoundary>
          <SetupMatchCard />
        </DashboardErrorBoundary>
      </div>

      <section className="rounded-[28px] border border-slate-200/80 bg-white shadow-[0_18px_50px_-40px_rgba(15,23,42,0.28)] dark:border-slate-800 dark:bg-[#0f172a]">
        <div className="flex items-center justify-between gap-4 border-b border-slate-100 p-6 dark:border-slate-800">
          <div className="flex items-center gap-3 text-slate-900 dark:text-white">
            <ClipboardList className="text-blue-600" size={16} />
            <span className="text-sm font-black uppercase tracking-[0.22em]">{copy.activeTitle}</span>
          </div>

          <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-4 py-2 focus-within:ring-4 focus-within:ring-blue-600/5 dark:border-slate-800 dark:bg-slate-950/50">
            <Search size={14} className="text-slate-400 dark:text-slate-500" />
            <input
              type="text"
              placeholder={copy.searchPlaceholder}
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              className="w-40 bg-transparent text-[11px] font-bold text-slate-700 outline-none dark:text-slate-300"
            />
          </div>
        </div>

        <SetupList
          setups={safeSetups}
          loading={loading}
          error={error}
          searchTerm={search}
          saveSetup={saveSetup}
          removeSetup={removeSetup}
          reload={reloadSetups}
        />
      </section>

      <section
        id="setup-new"
        className="scroll-mt-32 rounded-[28px] border border-slate-200/80 bg-white shadow-[0_18px_50px_-40px_rgba(15,23,42,0.28)] dark:border-slate-800 dark:bg-[#0f172a]"
      >
        <div className="border-b border-slate-100 p-6 dark:border-slate-800">
          <div className="flex items-center gap-3 text-slate-900 dark:text-white">
            <PlusCircle className="text-blue-600" size={16} />
            <span className="text-sm font-black uppercase tracking-[0.22em]">{copy.newTitle}</span>
          </div>
        </div>

        <div className="p-8">
          {showOnboardingGuide ? (
            <div className="mb-6 rounded-2xl border border-blue-100 bg-blue-50 px-4 py-3 text-sm font-semibold leading-relaxed text-slate-700">
              {setupGuideCopy.guidedConfigHint}
            </div>
          ) : null}

          <p className="mb-6 border-b border-slate-50 pb-4 text-[11px] font-black uppercase tracking-widest text-slate-400 dark:border-slate-800/50 dark:text-slate-500">
            {copy.newDescription}
          </p>

          <div className="mb-6 flex items-center gap-2 text-[11px] font-black uppercase tracking-[0.24em] text-blue-600 dark:text-blue-400">
            <Settings size={12} />
            Configuration
          </div>

          <SetupForm onSaved={reloadSetups} />
        </div>
      </section>
    </div>
  );
}
