"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, ArrowRight, CheckCircle2 } from "lucide-react";

import AddBotForm from "@/components/bot/AddBotForm";
import OnboardingBanner from "@/components/onboarding/OnboardingBanner";
import { useTranslation } from "@/app/providers/I18nProvider";
import useBotData from "@/hooks/useBotData";
import { useOnboarding } from "@/hooks/useOnboarding";
import { useStrategyData } from "@/hooks/useStrategyData";
import { getPlanStrategiesForAsset } from "@/lib/setup/activeSetup";

function AutomationStep() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { t } = useTranslation();
  const copy = t?.botPage || {};
  const guide = copy.onboardingGuide || {};
  const { status, loading: statusLoading, saving: savingStep, completeStep, error: onboardingError } = useOnboarding();
  const { strategies, setups, loading: strategiesLoading, error: strategiesError } = useStrategyData();
  const { configs: bots, createBot, loading: botLoading, error: botError } = useBotData();
  const [savedBot, setSavedBot] = useState(null);
  const [continuing, setContinuing] = useState(false);
  const [selectedStrategyId, setSelectedStrategyId] = useState("");
  const completionRequested = useRef(false);

  const requestedStrategyId = Number(searchParams.get("strategy_id"));
  const requestedStrategy = useMemo(() =>
    Number.isFinite(requestedStrategyId) && requestedStrategyId > 0
      ? strategies.find((item) => Number(item.id) === requestedStrategyId) || null
      : null,
  [requestedStrategyId, strategies]);
  const symbol = String(requestedStrategy?.symbol || searchParams.get("symbol") || status?.active_asset || "").toUpperCase();
  useEffect(() => {
    if (!requestedStrategy?.symbol || !requestedStrategyId || strategiesLoading) return;
    const actualSymbol = String(requestedStrategy.symbol).toUpperCase();
    if (String(searchParams.get("symbol") || "").toUpperCase() === actualSymbol) return;
    const nextParams = new URLSearchParams(searchParams.toString());
    nextParams.set("symbol", actualSymbol);
    router.replace(`/onboarding/automation?${nextParams.toString()}`);
  }, [requestedStrategy, requestedStrategyId, router, searchParams, strategiesLoading]);
  const availableStrategies = useMemo(() => getPlanStrategiesForAsset(symbol, strategies, setups), [strategies, setups, symbol]);
  const hasAssetPlan = availableStrategies.length > 0;
  const strategy = useMemo(() => {
    if (Number.isFinite(requestedStrategyId) && requestedStrategyId > 0) {
      return requestedStrategy;
    }
    if (availableStrategies.length === 1) return availableStrategies[0];
    return availableStrategies.find((item) => String(item.id) === selectedStrategyId) || null;
  }, [requestedStrategyId, requestedStrategy, availableStrategies, selectedStrategyId]);
  const setup = useMemo(() =>
    setups.find((item) => Number(item.id ?? item.setup_id) === Number(strategy?.setup_id)) || strategy?.setup || null,
  [setups, strategy]);
  const hasSelectedPlan = Boolean(strategy && availableStrategies.some((item) => Number(item.id) === Number(strategy.id)) && setup);
  const initialValues = useMemo(() => strategy ? ({
    name: searchParams.get("plan_name") || `${strategy.name} Bot`,
    symbol: symbol || strategy.symbol || "",
    strategy_id: strategy.id,
    is_live: searchParams.get("mode") === "live",
    mode: "manual",
    risk_profile: searchParams.get("risk") || "balanced",
    budget_total_eur: Number(searchParams.get("budget")) || 1000,
  }) : null, [strategy, symbol, searchParams]);
  const existingBot = useMemo(() => bots.find((item) =>
    Number(item.strategy_id || item.strategy?.id) === Number(strategy?.id)
  ) || null, [bots, strategy]);
  const completedBot = savedBot?.bot || savedBot || existingBot;
  const backHref = `/onboarding/plan?onboarding=1&step=setup${symbol ? `&symbol=${encodeURIComponent(symbol)}` : ""}`;

  useEffect(() => {
    if (statusLoading || !status) return;
    if (!status.has_asset) {
      router.replace("/onboarding/asset?onboarding=1&step=asset");
    }
  }, [backHref, router, status, statusLoading]);

  useEffect(() => {
    if (!completedBot || status?.has_bot || completionRequested.current) return;
    completionRequested.current = true;
    void completeStep("bot");
  }, [completedBot, status?.has_bot, completeStep]);

  const handleSaved = (bot) => {
    setSavedBot(bot);
  };

  const handleContinue = () => {
    setContinuing(true);
    router.push(symbol
      ? `/onboarding/complete?symbol=${encodeURIComponent(symbol)}`
      : "/onboarding/complete");
  };

  return (
    <div className="mx-auto max-w-5xl py-8">
      <OnboardingBanner step="bot" phaseStatusOverrides={{ plan: hasAssetPlan, automation: Boolean(completedBot && hasSelectedPlan) }} />

      <div className="mb-8 rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
        <div className="flex flex-wrap items-start justify-between gap-5">
          <div className="max-w-2xl">
            <div className="text-[10px] font-black uppercase tracking-[0.25em] text-blue-600">
              {guide.stepNumber || "Automation · 4 of 4"}
            </div>
            <h1 className="mt-3 text-3xl font-black tracking-tight text-slate-900">
              {guide.title || "Link one bot to your strategy"}
            </h1>
            <p className="mt-3 text-sm font-medium leading-relaxed text-slate-600">
              {guide.createStepSubtitle || "Create one bot for the strategy you just saved."}
            </p>
          </div>
          <button type="button" onClick={() => router.push(backHref)}
            className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 px-4 py-2 text-sm font-bold text-slate-600 hover:border-blue-200 hover:text-blue-700">
            <ArrowLeft size={16} /> {guide.secondaryReviewCta || "Back to My Plan"}
          </button>
        </div>
        <div className="mt-6 grid gap-3 sm:grid-cols-3">
          {[
            [guide.assetLabel || "Asset", symbol || "—"],
            [guide.setupLabel || "Setup", setup?.name || "—"],
            [guide.strategyLabel || "Strategy", strategy?.name || "—"],
          ].map(([label, value]) => (
            <div key={label} className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
              <div className="text-[10px] font-black uppercase tracking-[0.18em] text-slate-400">{label}</div>
              <div className="mt-1 text-sm font-black text-slate-900">{value}</div>
            </div>
          ))}
        </div>
      </div>

      {strategiesError || botError || onboardingError ? (
        <p role="alert" className="mb-6 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm font-semibold text-red-700">
          {strategiesError || botError || onboardingError}
        </p>
      ) : null}

      {!requestedStrategyId && availableStrategies.length > 1 ? (
        <div className="mb-6 rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
          <label htmlFor="onboarding-automation-strategy" className="block text-sm font-black text-slate-900">
            {copy.form?.strategyLabel || "Kies de strategie voor deze bot"}
          </label>
          <select id="onboarding-automation-strategy" value={selectedStrategyId}
            onChange={(event) => {
              setSelectedStrategyId(event.target.value);
              setSavedBot(null);
            }}
            className="mt-3 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-900 focus:border-blue-500">
            <option value="">{copy.form?.strategyPlaceholder || "Kies een strategie"}</option>
            {availableStrategies.map((item) => (
              <option key={item.id} value={item.id}>{item.name} · {item.symbol}</option>
            ))}
          </select>
        </div>
      ) : null}

      {statusLoading || strategiesLoading || botLoading.configs ? (
        <div className="rounded-[28px] border border-slate-200 bg-white p-8 text-sm font-semibold text-slate-500">
          {guide.pendingLabel || "Loading…"}
        </div>
      ) : completedBot ? (
        <section className="rounded-[28px] border border-emerald-200 bg-emerald-50 p-6 shadow-sm sm:p-8">
          <div className="flex items-center gap-2 text-sm font-black text-emerald-800">
            <CheckCircle2 size={20} /> {guide.completedTitle || "Your first execution flow is ready"}
          </div>
          <p className="mt-3 text-sm font-medium text-slate-700">
            {completedBot.name} · {completedBot.is_live ? copy.modeLive : copy.modePaper}
          </p>
          <p className="mt-2 text-sm text-slate-600">
            {guide.completedBody || "Your bot is linked to your plan. You can review its settings in Automation after onboarding."}
          </p>
          <button type="button" onClick={handleContinue} disabled={continuing || !status?.has_bot}
            className="mt-6 inline-flex items-center gap-2 rounded-2xl bg-blue-600 px-5 py-3 text-sm font-black text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60">
            {guide.nextCta || "Finish onboarding"} <ArrowRight size={16} />
          </button>
          {onboardingError && !status?.has_bot ? (
            <button type="button" onClick={() => void completeStep("bot")} disabled={savingStep}
              className="ml-3 text-sm font-bold text-blue-700 underline disabled:opacity-60">
              {t?.common?.retry || "Opnieuw proberen"}
            </button>
          ) : null}
        </section>
      ) : hasSelectedPlan && initialValues ? (
        <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
          <AddBotForm
            strategies={strategies}
            setups={setups}
            initialValues={initialValues}
            guidedMode
            guidedSymbol={symbol}
            hideActions={false}
            submitLabel={copy.createConfirm}
            submitBusyLabel={copy.createBusy}
            cancelLabel={t?.common?.back || "Terug"}
            successMessage={copy.createSuccess}
            saveFailedMessage={copy.form?.saveFailed || copy.createValidation}
            onCancel={() => router.push(backHref)}
            onSubmit={createBot}
            onSaved={handleSaved}
          />
        </section>
      ) : availableStrategies.length > 1 && !selectedStrategyId && !requestedStrategyId ? null : (
        <section className="rounded-[28px] border border-amber-200 bg-amber-50 p-6 text-sm font-semibold text-amber-800">
          {guide.lockedBody || "Save a strategy before creating the bot."}
          <button type="button" onClick={() => router.push(backHref)} className="mt-4 block font-black underline">
            {guide.secondaryReviewCta || "Back to My Plan"}
          </button>
        </section>
      )}
    </div>
  );
}

export default function OnboardingAutomationPage() {
  return <Suspense fallback={null}><AutomationStep /></Suspense>;
}
