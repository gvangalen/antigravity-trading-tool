"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useModal } from "@/components/modal/ModalProvider";
import {
  ClipboardList,
  PlusCircle,
  Search,
  ShieldCheck,
  Zap,
  Activity,
} from "lucide-react";

import StrategyList from "@/components/strategy/StrategyList";
import StrategyForm from "@/components/strategy/StrategyForm";
import ActiveStrategyTodayCard from "@/components/strategy/ActiveStrategyTodayCard";
import AgentInsightPanel from "@/components/agents/AgentInsightPanel";
import OnboardingBanner from "@/components/onboarding/OnboardingBanner";
import OnboardingStepGuide from "@/components/onboarding/OnboardingStepGuide";
import Drawer from "@/components/ui/Drawer";
import DashboardErrorBoundary from "@/components/ui/DashboardErrorBoundary";
import { useSetupData } from "@/hooks/useSetupData";
import { useStrategyData } from "@/hooks/useStrategyData";
import { useOnboarding } from "@/hooks/useOnboarding";
import { createStrategy, deleteStrategy, updateStrategy } from "@/lib/api/strategy";
import { useTranslation } from "@/app/providers/I18nProvider";

export default function StrategiesWorkspaceSection() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { showSnackbar } = useModal();
  const { t } = useTranslation();
  const { status, completeStep } = useOnboarding();
  const copy = t?.strategyPage || {};
  const strategyGuideCopy = copy.onboardingGuide || {};
  const feedback = copy.feedback || {};

  const [search, setSearch] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [editingStrategy, setEditingStrategy] = useState(null);

  const { setups, loadSetups } = useSetupData();
  const { strategies, loadStrategies, loading: strategyLoading } = useStrategyData();

  const safeSetups = Array.isArray(setups) ? setups : [];
  const safeStrategies = Array.isArray(strategies) ? strategies : [];
  const strategyStepComplete = Boolean(status?.has_strategy || safeStrategies.length > 0);
  const strategyNeedsSetup = status?.has_strategy === false && safeStrategies.length === 0;
  const onboardingGuidedMode = searchParams.get("onboarding") === "1";
  const showOnboardingGuide = onboardingGuidedMode || strategyNeedsSetup;

  useEffect(() => {
    if (!status || status.has_asset) return;
    router.replace("/onboarding/asset?onboarding=1&step=asset");
  }, [status, router]);

  useEffect(() => {
    loadSetups();
    loadStrategies();
  }, [loadSetups, loadStrategies]);

  useEffect(() => {
    if (safeStrategies.length > 0 && status && status.has_strategy === false) {
      completeStep("strategy");
    }
  }, [safeStrategies, status, completeStep]);

  const refreshEverything = () => {
    loadStrategies();
    loadSetups();
    setTimeout(() => setRefreshKey((current) => current + 1), 30);
  };

  const handleDeleteStrategy = async (id) => {
    try {
      await deleteStrategy(id);
      showSnackbar(feedback.deleted || "Strategy removed.", "success");
      refreshEverything();
    } catch {
      showSnackbar(feedback.deleteFailed || "Deleting the strategy failed.", "danger");
    }
  };

  const handleUpdateStrategy = async (id, data) => {
    try {
      await updateStrategy(id, data);
      showSnackbar(feedback.updated || "Strategy updated.", "success");
      setEditingStrategy(null);
      refreshEverything();
    } catch {
      showSnackbar(feedback.updateFailed || "Updating the strategy failed.", "danger");
    }
  };

  const handleStrategySubmit = async (strategy) => {
    try {
      const setup = safeSetups.find((item) => String(item.id) === String(strategy.setup_id));
      if (!setup) {
        showSnackbar(feedback.invalidSetup || "Choose a valid setup first.", "danger");
        return;
      }

      await createStrategy({
        ...strategy,
        setup_id: setup.id,
        setup_type: setup.setup_type,
      });

      showSnackbar(feedback.saved || "Strategy saved.", "success");
      refreshEverything();
    } catch {
      showSnackbar(feedback.saveFailed || "Saving the strategy failed.", "danger");
    }
  };

  return (
    <div className="space-y-8">
      <OnboardingBanner step="strategy" />

      {showOnboardingGuide ? (
        <OnboardingStepGuide
          copy={strategyGuideCopy}
          anchorId="strategy-new"
          guidedMode={onboardingGuidedMode}
          isComplete={strategyStepComplete}
          nextHref="/bot?onboarding=1&step=bot"
          assistantFlow="strategy_creation"
          assistantSuppressRestore
        />
      ) : null}

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <div className="rounded-[28px] border border-slate-200/80 bg-white p-8 text-center shadow-[0_18px_50px_-40px_rgba(15,23,42,0.28)] dark:border-slate-800 dark:bg-[#0f172a]">
          <div className="mb-4 text-[10px] font-black uppercase tracking-[0.25em] text-slate-400 dark:text-slate-500">
            {copy.activePlans}
          </div>
          <div className="text-5xl font-black tracking-tighter text-blue-600 dark:text-blue-400">
            {safeStrategies.filter((strategy) => strategy.is_active).length}
          </div>
        </div>
        <div className="rounded-[28px] border border-slate-200/80 bg-white p-8 text-center shadow-[0_18px_50px_-40px_rgba(15,23,42,0.28)] dark:border-slate-800 dark:bg-[#0f172a]">
          <div className="mb-4 text-[10px] font-black uppercase tracking-[0.25em] text-slate-400 dark:text-slate-500">
            {copy.total}
          </div>
          <div className="text-5xl font-black tracking-tighter text-slate-900 dark:text-slate-100">
            {safeStrategies.length}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <DashboardErrorBoundary>
            <AgentInsightPanel category="strategy" key={refreshKey} />
          </DashboardErrorBoundary>
        </div>
        <div className="lg:col-span-1">
          <DashboardErrorBoundary>
            <ActiveStrategyTodayCard />
          </DashboardErrorBoundary>
        </div>
      </div>

      <section className="rounded-[28px] border border-slate-200/80 bg-white shadow-[0_18px_50px_-40px_rgba(15,23,42,0.28)] dark:border-slate-800 dark:bg-[#0f172a]">
        <div className="flex items-center justify-between gap-4 border-b border-slate-100 p-6 dark:border-slate-800">
          <div className="flex items-center gap-3 text-slate-900 dark:text-white">
            <ClipboardList size={16} className="text-blue-600" />
            <span className="text-sm font-black uppercase tracking-[0.22em]">{copy.overview}</span>
          </div>

          <div className="flex items-center rounded-xl border border-slate-200 bg-slate-50 px-4 py-2 focus-within:ring-4 focus-within:ring-blue-600/5 dark:border-slate-800 dark:bg-slate-950/50">
            <Search size={14} className="mr-2 text-slate-400 dark:text-slate-500" />
            <input
              type="text"
              placeholder={copy.searchPlaceholder}
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              className="w-40 bg-transparent text-[11px] font-bold text-slate-700 outline-none dark:text-slate-300"
            />
          </div>
        </div>

        <DashboardErrorBoundary>
          <StrategyList
            strategies={safeStrategies}
            searchTerm={search}
            onRefresh={refreshEverything}
            onDelete={handleDeleteStrategy}
            onUpdate={handleUpdateStrategy}
            onEdit={setEditingStrategy}
            loading={strategyLoading}
            key={refreshKey}
          />
        </DashboardErrorBoundary>
      </section>

      <section
        id="strategy-new"
        className="scroll-mt-32 rounded-[28px] border border-slate-200/80 bg-white shadow-[0_18px_50px_-40px_rgba(15,23,42,0.28)] dark:border-slate-800 dark:bg-[#0f172a]"
      >
        <div className="border-b border-slate-100 p-6 dark:border-slate-800">
          <div className="flex items-center gap-3 text-slate-900 dark:text-white">
            <PlusCircle size={16} className="text-blue-600" />
            <span className="text-sm font-black uppercase tracking-[0.22em]">{copy.newTitle}</span>
          </div>
        </div>

        <div className="p-8">
          {showOnboardingGuide ? (
            <div className="mb-6 rounded-2xl border border-blue-100 bg-blue-50 px-4 py-3 text-sm font-semibold leading-relaxed text-slate-700">
              {strategyGuideCopy.guidedConfigHint}
            </div>
          ) : null}

          <p className="mb-6 border-b border-slate-50 pb-4 text-[11px] font-black uppercase tracking-widest text-slate-400 dark:border-slate-800/50 dark:text-slate-500">
            {copy.newDescription}
          </p>

          <StrategyForm key={refreshKey} onSubmit={handleStrategySubmit} setups={safeSetups} />
        </div>
      </section>

      <Drawer
        isOpen={!!editingStrategy}
        onClose={() => setEditingStrategy(null)}
        title={editingStrategy?.name || copy.editTitle}
        subtitle={copy.editSubtitle}
      >
        {editingStrategy ? (
          <StrategyForm
            strategy={editingStrategy}
            setups={safeSetups}
            onSubmit={(data) => handleUpdateStrategy(editingStrategy.id, data)}
            isEdit
          />
        ) : null}
      </Drawer>

      <footer className="flex items-center justify-center gap-12 border-t border-slate-100 py-16 opacity-60 dark:border-slate-800">
        <div className="flex items-center gap-3 text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 dark:text-slate-500">
          <Zap size={14} className="text-blue-500" /> {copy.footerFast}
        </div>
        <div className="flex items-center gap-3 text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 dark:text-slate-500">
          <ShieldCheck size={14} className="text-blue-600" /> {copy.footerSafe}
        </div>
      </footer>
    </div>
  );
}
