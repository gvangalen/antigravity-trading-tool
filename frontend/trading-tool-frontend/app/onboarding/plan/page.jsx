"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { ArrowRight, CheckCircle2, Lock, Sparkles } from "lucide-react";

import { useTranslation } from "@/app/providers/I18nProvider";
import OnboardingBanner from "@/components/onboarding/OnboardingBanner";
import { useOnboarding } from "@/hooks/useOnboarding";
import { fetchLastSetup, fetchSetups, saveNewSetup, updateSetup } from "@/lib/api/setups";
import { fetchTradingMarkets } from "@/lib/api/assets";
import MarketConditionPicker from "@/components/setup/MarketConditionPicker";
import { MARKET_CONDITIONS, marketConditionChoiceFromSetup, marketConditionPayload } from "@/lib/setup/scoreConditions.mjs";
import { createStrategy, fetchLastStrategy, fetchStrategies, fetchStrategyBySetup, updateStrategy } from "@/lib/api/strategy";
import { fetchBotConfigs } from "@/lib/api/botApi";
import { resolveSavedOnboardingPlan, setupPatchForOnboarding, strategyPatchForOnboarding } from "@/lib/onboarding/planEdits.mjs";
import {
  findSavedSetupForAsset,
  getPlanCompletionForAsset,
  getSetupId,
  normalizeSetupSaveResponse,
} from "@/lib/setup/activeSetup";

const DEFAULT_SETUP = {
  name: "",
  setupType: "dca",
  timeframe: "1D",
  dcaFrequency: "weekly",
  dcaDay: "monday",
  dcaMonthDay: "1",
  min_benchmark_score: 46, max_benchmark_score: 60,
};
const DCA_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];

function setupDraftFromSaved(candidate, symbol) {
  return {
    name: candidate.name || `${symbol} Setup`,
    setupType: String(candidate.setup_type || "trade").toLowerCase(),
    timeframe: candidate.timeframe || "4H",
    dcaFrequency: candidate.dca_frequency || "weekly",
    dcaDay: DCA_WEEKDAYS[Number(candidate.dca_day) - 1] || candidate.dca_day || "monday",
    dcaMonthDay: String(candidate.dca_month_day || 1),
    min_benchmark_score: candidate.min_benchmark_score ?? DEFAULT_SETUP.min_benchmark_score,
    max_benchmark_score: candidate.max_benchmark_score ?? DEFAULT_SETUP.max_benchmark_score,
  };
}

function strategyDraftFromSaved(candidate, symbol) {
  return {
    name: candidate.name || `${symbol} Strategy`,
    executionMode: candidate.execution_mode || "fixed",
    baseAmount: String(candidate.base_amount ?? candidate.amount ?? 100),
    entry: candidate.entry != null ? String(candidate.entry) : "",
    targets: Array.isArray(candidate.targets)
      ? candidate.targets.map((item) => (typeof item === "object" ? item.price : item)).join(", ")
      : "",
    stopLoss: candidate.stop_loss != null ? String(candidate.stop_loss) : "",
  };
}

const DEFAULT_STRATEGY = {
  name: "",
  executionMode: "fixed",
  baseAmount: "",
  entry: "",
  targets: "",
  stopLoss: "",
};

function Section({ title, subtitle, children, status, savedLabel }) {
  return (
    <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-black tracking-tight text-slate-900">{title}</h2>
          <p className="mt-1 text-sm font-medium leading-relaxed text-slate-500">{subtitle}</p>
        </div>
        {status ? (
          <span className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-[10px] font-black uppercase tracking-[0.18em] text-emerald-700">
            <CheckCircle2 size={12} />
            {savedLabel || "Saved"}
          </span>
        ) : null}
      </div>
      {children}
    </section>
  );
}

function SummaryRow({ label, value }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
      <span className="text-[10px] font-black uppercase tracking-[0.18em] text-slate-400">{label}</span>
      <span className="text-sm font-black text-slate-900">{value}</span>
    </div>
  );
}

function ProgressStep({ index, title, subtitle, active, complete, locked }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white px-4 py-4">
      <div className="flex items-start gap-3">
        <div
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl text-sm font-black ${
            complete
              ? "bg-emerald-100 text-emerald-700"
              : active
                ? "bg-blue-600 text-white"
                : locked
                  ? "bg-slate-100 text-slate-400"
                  : "bg-blue-50 text-blue-700"
          }`}
        >
          {complete ? <CheckCircle2 size={16} /> : index}
        </div>
        <div className="min-w-0">
          <div className="text-base font-black tracking-tight text-slate-900">{title}</div>
          <div className="mt-1 text-sm font-medium leading-relaxed text-slate-500">{subtitle}</div>
        </div>
      </div>
    </div>
  );
}

function Field({ label, hint, children }) {
  return (
    <label className="block space-y-2">
      <span className="text-sm font-semibold text-slate-700">{label}</span>
      {children}
      {hint ? <span className="block text-xs font-medium text-slate-500">{hint}</span> : null}
    </label>
  );
}

const inputClassName =
  "w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-900 outline-none transition focus:border-blue-300";

export default function OnboardingPlanPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { t } = useTranslation();
  const { status, completeStep } = useOnboarding();
  const strategySectionRef = useRef(null);
  const completionSectionRef = useRef(null);

  const symbol = useMemo(
    () => String(searchParams.get("symbol") || status?.active_asset || "BTC").toUpperCase(),
    [searchParams, status?.active_asset],
  );
  const requestedSetupId = Number(searchParams.get("setup_id"));
  const requestedStrategyId = Number(searchParams.get("strategy_id"));

  const copy = t?.traderProfile?.planOnboardingStep || {};

  const [loading, setLoading] = useState(true);
  const [continuing, setContinuing] = useState(false);
  const [savingSetup, setSavingSetup] = useState(false);
  const [savingStrategy, setSavingStrategy] = useState(false);
  const [error, setError] = useState(null);
  const [selectionUnavailable, setSelectionUnavailable] = useState(false);

  const [setup, setSetup] = useState(DEFAULT_SETUP);
  const [conditionChoice, setConditionChoice] = useState("off");
  const [strategy, setStrategy] = useState(DEFAULT_STRATEGY);
  const [savedSetup, setSavedSetup] = useState(null);
  const [savedStrategy, setSavedStrategy] = useState(null);
  const [marketChoices, setMarketChoices] = useState([]);
  const [marketChoiceStatus, setMarketChoiceStatus] = useState("loading");
  const [quoteCurrency, setQuoteCurrency] = useState("");
  const [editingSetup, setEditingSetup] = useState(false);
  const [reviewingSetup, setReviewingSetup] = useState(false);
  const [setupScoreTouched, setSetupScoreTouched] = useState(false);
  const [editingStrategy, setEditingStrategy] = useState(false);
  const [reviewingStrategy, setReviewingStrategy] = useState(false);
  const [bots, setBots] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setMarketChoices([]);
    setQuoteCurrency("");
    setMarketChoiceStatus("loading");
    fetchTradingMarkets(symbol).then((result) => {
      if (cancelled) return;
      if (!Array.isArray(result) && result?.asset_class !== "crypto") {
        setMarketChoiceStatus("not_crypto");
        return;
      }
      const available = (Array.isArray(result) ? result : (Array.isArray(result?.markets) ? result.markets : []))
        .filter((choice) => choice?.status === "available" && choice?.quote_currency);
      setMarketChoices(available);
      setMarketChoiceStatus(available.length ? "ready" : "unavailable");
    }).catch((error) => {
      if (!cancelled) setMarketChoiceStatus(error?.status === 404 ? "not_crypto" : "error");
    });
    return () => { cancelled = true; };
  }, [symbol]);

  useEffect(() => {
    let cancelled = false;

    async function loadExisting() {
      try {
        setLoading(true);
        setError(null);
        setSelectionUnavailable(false);
        setSavedSetup(null);
        setSavedStrategy(null);
        setSetup(DEFAULT_SETUP);
        setStrategy(DEFAULT_STRATEGY);
        setConditionChoice("off");
        setEditingSetup(false);
        setReviewingSetup(false);
        setSetupScoreTouched(false);
        setEditingStrategy(false);
        setReviewingStrategy(false);

        const [lastSetup, savedSetups, lastStrategy, botConfigs, savedStrategies] = await Promise.all([
          fetchLastSetup().catch(() => null),
          fetchSetups(),
          fetchLastStrategy().catch(() => null),
          fetchBotConfigs().catch(() => null),
          requestedStrategyId > 0 ? fetchStrategies(symbol) : Promise.resolve([]),
        ]);

        if (cancelled) return;
        setBots(botConfigs);

        const selected = resolveSavedOnboardingPlan({
          symbol, setups: savedSetups, strategies: savedStrategies,
          fallbackSetup: findSavedSetupForAsset(symbol, lastSetup, savedSetups),
          setupId: requestedSetupId, strategyId: requestedStrategyId,
        });
        if (selected.invalid) {
          setError(copy.planSelectionError || "The selected plan is no longer available. Go back to My Plan and choose it again.");
          setSelectionUnavailable(true);
          return;
        }
        const setupCandidate = selected.setup;
        const exactStrategy = selected.strategy;

        if (setupCandidate) {
          setConditionChoice(marketConditionChoiceFromSetup(setupCandidate));
          const setupId = getSetupId(setupCandidate);
          setSavedSetup(setupCandidate);
          setSetup(setupDraftFromSaved(setupCandidate, symbol));

          const bySetup = exactStrategy || (setupId
            ? await fetchStrategyBySetup(setupId).catch(() => null)
            : null);
          if (!cancelled && bySetup) {
            setSavedStrategy({ setup_id: setupId, ...bySetup });
            setStrategy(strategyDraftFromSaved(bySetup, symbol));
          } else if (!cancelled && Number(lastStrategy?.strategy?.setup_id) === Number(setupId)) {
            setSavedStrategy(lastStrategy.strategy);
            setStrategy(strategyDraftFromSaved(lastStrategy.strategy, symbol));
          }
        }
      } catch (err) {
        console.error("Failed to load onboarding plan step", err);
        if (!cancelled) {
          setError(copy.loadError || "Loading the My Plan onboarding step failed.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadExisting();
    return () => {
      cancelled = true;
    };
  }, [copy.loadError, copy.planSelectionError, requestedSetupId, requestedStrategyId, symbol]);

  const { setupDone, strategyDone } = getPlanCompletionForAsset(symbol, savedSetup, savedStrategy);
  const isTrade = String(setup.setupType || "").toLowerCase() === "trade";

  const setupValid = Boolean(
    setup.name.trim() && setup.setupType && setup.timeframe &&
    (setupDone || marketChoiceStatus === "not_crypto" ||
      (marketChoiceStatus === "ready" && quoteCurrency)) &&
    conditionChoice && (conditionChoice !== "off" || !isTrade || setupDone) &&
    (conditionChoice !== "custom" || (() => {
      const minimum = Number(setup.min_benchmark_score);
      const maximum = Number(setup.max_benchmark_score);
      return setup.min_benchmark_score !== "" && setup.max_benchmark_score !== "" &&
        Number.isFinite(minimum) && Number.isFinite(maximum) &&
        minimum >= 0 && maximum <= 100 && minimum <= maximum;
    })()) &&
    (isTrade || (
      setup.dcaFrequency &&
      (setup.dcaFrequency !== "weekly" || setup.dcaDay) &&
      (setup.dcaFrequency !== "monthly" || (
        Number.isInteger(Number(setup.dcaMonthDay)) &&
        Number(setup.dcaMonthDay) >= 1 && Number(setup.dcaMonthDay) <= 28
      ))
    )),
  );
  const strategyValid = Boolean(
    strategy.name.trim() &&
      Number(strategy.baseAmount) > 0 &&
      (!isTrade || (strategy.entry.trim() && strategy.targets.trim() && strategy.stopLoss.trim())),
  );
  const setupPatch = setupDone ? setupPatchForOnboarding(savedSetup, setup, conditionChoice, setupScoreTouched) : {};
  const strategyPatch = strategyDone ? strategyPatchForOnboarding(savedStrategy, strategy, isTrade) : {};
  const linkedBots = Array.isArray(bots)
    ? bots.filter((bot) => Number(bot.strategy_id ?? bot.strategy?.id) === Number(savedStrategy?.strategy_id ?? savedStrategy?.id))
    : [];
  const scoreCurvePoints = savedStrategy?.execution_mode === "custom" && Array.isArray(savedStrategy?.decision_curve?.points)
    ? [...savedStrategy.decision_curve.points].sort((left, right) => Number(left.x) - Number(right.x))
    : [];
  const scoreCurveIsStep = savedStrategy?.decision_curve?.interpolation === "step";
  const scoreCurveTitle = scoreCurveIsStep ? copy.savedScoreCurveLabel : copy.savedLinearCurveLabel;
  const scoreCurvePointPrefix = scoreCurveIsStep ? copy.fromScore : copy.atScore;
  const scoreCurveDescription = scoreCurvePoints.map((point) =>
    `${scoreCurvePointPrefix} ${point.x}: ${Math.round(Number(point.y) * 100)}% · €${(Number(strategy.baseAmount) * Number(point.y)).toFixed(2)}`
  ).join(" · ");
  const setupReadOnly = setupDone && (!editingSetup || reviewingSetup);
  const strategyReadOnly = strategyDone && (!editingStrategy || reviewingStrategy);

  const cancelSetupEdit = () => {
    setSetup(setupDraftFromSaved(savedSetup, symbol));
    setConditionChoice(marketConditionChoiceFromSetup(savedSetup));
    setSetupScoreTouched(false);
    setReviewingSetup(false);
    setEditingSetup(false);
    setError(null);
  };

  const cancelStrategyEdit = () => {
    setStrategy(strategyDraftFromSaved(savedStrategy, symbol));
    setReviewingStrategy(false);
    setEditingStrategy(false);
    setError(null);
  };

  const handleUpdateSetup = async () => {
    if (!setupValid || !Object.keys(setupPatch).length || !getSetupId(savedSetup)) return;
    try {
      setSavingSetup(true);
      setError(null);
      const response = await updateSetup(getSetupId(savedSetup), setupPatch, { silent: true });
      const updated = response?.setup || { ...savedSetup, ...setupPatch };
      setSavedSetup(updated);
      setSetup(setupDraftFromSaved(updated, symbol));
      setConditionChoice(marketConditionChoiceFromSetup(updated));
      setSetupScoreTouched(false);
      setReviewingSetup(false);
      setEditingSetup(false);
    } catch (err) {
      console.error("Failed to update onboarding setup", err);
      setError(copy.setupUpdateError || "Updating the setup failed. Your changes were not saved.");
    } finally {
      setSavingSetup(false);
    }
  };

  const handleUpdateStrategy = async () => {
    const strategyId = savedStrategy?.strategy_id ?? savedStrategy?.id;
    if (!strategyValid || !Object.keys(strategyPatch).length || !strategyId) return;
    try {
      setSavingStrategy(true);
      setError(null);
      await updateStrategy(strategyId, strategyPatch);
      const updated = { ...savedStrategy, ...strategyPatch };
      setSavedStrategy(updated);
      setStrategy(strategyDraftFromSaved(updated, symbol));
      setReviewingStrategy(false);
      setEditingStrategy(false);
    } catch (err) {
      console.error("Failed to update onboarding strategy", err);
      setError(copy.strategyUpdateError || "Updating the strategy failed. Your changes were not saved.");
    } finally {
      setSavingStrategy(false);
    }
  };

  const handleSaveSetup = async () => {
    if (!setupValid) {
      setError(copy.setupValidationError || "Complete the setup fields first.");
      return;
    }

    try {
      setSavingSetup(true);
      setError(null);

      const response = await saveNewSetup({
        name: setup.name.trim(),
        symbol,
        ...(quoteCurrency ? { quote_currency: quoteCurrency } : {}),
        setup_type: setup.setupType,
        timeframe: setup.timeframe,
        ...marketConditionPayload(conditionChoice, {
          min_benchmark_score: Number(setup.min_benchmark_score),
          max_benchmark_score: Number(setup.max_benchmark_score),
        }),
        ...(isTrade ? {} : {
          dca_frequency: setup.dcaFrequency,
          dca_day: setup.dcaFrequency === "weekly" ? setup.dcaDay : null,
          dca_month_day: setup.dcaFrequency === "monthly" ? Number(setup.dcaMonthDay) : null,
        }),
      });

      const nextSetup = normalizeSetupSaveResponse(response);
      if (!nextSetup) {
        throw new Error("setup-save-response-missing-id");
      }
      setSavedSetup({ ...nextSetup, symbol });

      if (!status?.has_setup) {
        await completeStep("setup");
      }

      window.setTimeout(() => {
        completionSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 150);
    } catch (err) {
      console.error("Failed to save onboarding setup", err);
      setError(copy.setupSaveError || "Saving the setup failed. Try again.");
    } finally {
      setSavingSetup(false);
    }
  };

  const handleSaveStrategy = async () => {
    if (!setupDone) {
      setError(copy.strategyNeedsSetup || "Save the setup first.");
      return;
    }

    if (!strategyValid) {
      setError(copy.strategyValidationError || "Complete the strategy fields first.");
      return;
    }

    try {
      setSavingStrategy(true);
      setError(null);

      const payload = {
        name: strategy.name.trim(),
        setup_id: getSetupId(savedSetup),
        base_amount: Number(strategy.baseAmount),
        execution_mode: strategy.executionMode,
        setup_type: setup.setupType,
      };

      if (isTrade) {
        payload.entry = Number(strategy.entry);
        payload.targets = strategy.targets
          .split(",")
          .map((item) => Number(item.trim()))
          .filter((value) => Number.isFinite(value));
        payload.stop_loss = Number(strategy.stopLoss);
      }

      const response = await createStrategy(payload);
      setSavedStrategy({ ...payload, ...(response?.strategy ?? response ?? {}) });

      if (!status?.has_strategy) {
        await completeStep("strategy");
      }
    } catch (err) {
      console.error("Failed to save onboarding strategy", err);
      setError(copy.strategySaveError || "Saving the strategy failed. Try again.");
    } finally {
      setSavingStrategy(false);
    }
  };

  const handleContinue = () => {
    if (editingSetup || editingStrategy || savingSetup || savingStrategy) return;
    setContinuing(true);
    router.push(`/onboarding/complete?symbol=${encodeURIComponent(symbol)}`);
  };

  const reviewReady = setupDone;
  const savedCondition = MARKET_CONDITIONS.find(({ id }) => id === conditionChoice);
  const savedLegacyRanges = [
    ["market", savedSetup?.min_market_score, savedSetup?.max_market_score],
    ["macro", savedSetup?.min_macro_score, savedSetup?.max_macro_score],
    ["technical", savedSetup?.min_technical_score, savedSetup?.max_technical_score],
  ].filter(([, minimum, maximum]) => minimum != null || maximum != null);
  const conditionLabel = conditionChoice === "off"
    ? t?.setups?.marketConditions?.offTitle || "No extra score condition"
    : conditionChoice === "custom"
      ? savedLegacyRanges.length
        ? savedLegacyRanges.map(([category, minimum, maximum]) =>
          `${copy.scoreCategories?.[category] || category} ${minimum ?? "—"}–${maximum ?? "—"}`
        ).join(" · ")
        : `${savedSetup?.min_benchmark_score ?? setup.min_benchmark_score}–${savedSetup?.max_benchmark_score ?? setup.max_benchmark_score}`
      : savedCondition
        ? `${t?.setups?.marketConditions?.options?.[conditionChoice]?.title || savedCondition.id} (${savedCondition.min}–${savedCondition.max})`
        : "—";
  const reviewConditionLabel = conditionChoice === "custom" && (setupScoreTouched || !savedLegacyRanges.length)
    ? `${setup.min_benchmark_score}–${setup.max_benchmark_score}`
    : conditionLabel;

  if (selectionUnavailable && !loading) {
    return <div className="mx-auto max-w-3xl py-12">
      <div className="rounded-3xl border border-amber-200 bg-amber-50 p-8 text-slate-900">
        <p className="font-semibold">{error}</p>
        <Link href="/setup" className="mt-4 inline-block font-semibold text-blue-700 underline">
          {copy.editSavedPlan || "Choose a plan in My Plan"}
        </Link>
      </div>
    </div>;
  }

  return (
    <div className="mx-auto max-w-5xl py-8">
      <OnboardingBanner step="setup" phaseStatusOverrides={{ plan: setupDone }} />

      <div className="mb-10 rounded-3xl border border-slate-200 bg-white p-8 shadow-sm">
        <div className="flex flex-col gap-6 md:flex-row md:items-start md:justify-between">
          <div className="max-w-2xl">
            <div className="text-[10px] font-black uppercase tracking-[0.25em] text-blue-600">
              {copy.stepNumber || "My Plan · 3 of 4"}
            </div>
            <h1 className="mt-3 text-3xl font-black tracking-tight text-slate-900">
              {copy.title || "Create one setup and one strategy"}
            </h1>
            <p className="mt-4 text-sm font-medium leading-relaxed text-slate-500">
              {(copy.description || "Turn the first analysis around {symbol} into a concrete plan.").replace("{symbol}", symbol)}
            </p>
          </div>

          <div className="rounded-2xl border border-blue-100 bg-blue-50 px-4 py-3 text-sm font-semibold leading-relaxed text-slate-700">
            <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-blue-600">
              <Sparkles size={14} />
              {copy.finnSaysLabel || "Finn says"}
            </div>
            <p className="mt-2 max-w-sm">
              {(copy.finnSaysBody || "Keep this first plan simple: one setup and one linked strategy are enough to continue.").replace("{symbol}", symbol)}
            </p>
          </div>
        </div>
      </div>

      <section className="mb-5 rounded-[28px] border border-slate-200 bg-white p-5 shadow-sm">
        <div className="grid gap-3 md:grid-cols-3">
          <SummaryRow label={copy.assetLabel || "Asset"} value={symbol} />
          <SummaryRow
            label={copy.setupProgressLabel || "Setup progress"}
            value={setupDone ? copy.savedLabel || "Saved" : copy.pendingLabel || "Pending"}
          />
          <SummaryRow
            label={copy.strategyProgressLabel || "Strategy progress"}
            value={strategyDone ? copy.savedLabel || "Saved" : copy.pendingLabel || "Pending"}
          />
        </div>
      </section>

      <section className="mb-6 grid gap-3 md:grid-cols-3">
        <ProgressStep
          index="1"
          title={copy.setupTitle || "1. Setup"}
          subtitle={copy.setupSubtitle || "Save the first setup for this asset."}
          active={!setupDone}
          complete={setupDone}
          locked={false}
        />
        <ProgressStep
          index="2"
          title={copy.strategyTitle || "2. Strategy"}
          subtitle={copy.strategySubtitle || "Link one strategy to the setup you just saved."}
          active={setupDone && !strategyDone}
          complete={strategyDone}
          locked={!setupDone}
        />
        <ProgressStep
          index="3"
          title={copy.reviewTitle || "3. Review"}
          subtitle={copy.reviewSubtitle || "Check your first plan before you continue to Automation."}
          active={reviewReady}
          complete={false}
          locked={!reviewReady}
        />
      </section>

      <div className="grid gap-5">
        <Section
          title={copy.setupTitle || "1. Setup"}
          subtitle={copy.setupSubtitle || "Define the first setup that belongs to this asset."}
          status={setupDone}
          savedLabel={copy.savedLabel}
        >
          <div className="grid gap-4 md:grid-cols-3">
            {(marketChoiceStatus !== "not_crypto" || savedSetup?.quote_currency) ? (
              <Field label={copy.tradingMarketLabel}>
                <select value={savedSetup?.quote_currency || quoteCurrency}
                  onChange={(event) => setQuoteCurrency(event.target.value)}
                  disabled={setupDone || marketChoiceStatus !== "ready" || savingSetup || loading}
                  className={inputClassName}>
                  <option value="">{copy.tradingMarketChoose}</option>
                  {marketChoices.map((choice) => (
                    <option key={choice.pair} value={choice.quote_currency}>{choice.pair}</option>
                  ))}
                  {savedSetup?.quote_currency && !marketChoices.some((choice) => choice.quote_currency === savedSetup.quote_currency) ?
                    <option value={savedSetup.quote_currency}>{symbol}/{savedSetup.quote_currency}</option> : null}
                </select>
                {["error", "unavailable"].includes(marketChoiceStatus) && !setupDone ?
                  <span className="mt-1 block text-xs text-amber-700">{copy.tradingMarketUnavailable}</span> : null}
              </Field>
            ) : null}
            <Field label={copy.setupNameLabel || "Setup name"} hint={copy.setupNameHint || "Give your setup a recognizable name."}>
              <input
                type="text"
                value={setup.name}
                onChange={(event) => setSetup((current) => ({ ...current, name: event.target.value }))}
                placeholder={copy.setupNamePlaceholder || "E.g. Smart DCA – 200MA"}
                disabled={setupReadOnly || savingSetup || loading}
                className={inputClassName}
              />
            </Field>

            <Field label={copy.setupTypeLabel || "Type"} hint={!setupDone ? copy.onboardingDcaOnlyHint : undefined}>
              <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-semibold text-slate-900">
                {isTrade ? copy.setupTypeTrade || "Trade" : copy.setupTypeDca || "DCA"}
              </div>
            </Field>

            <Field label={copy.setupTimeframeLabel || "Timeframe"}>
              <select
                value={setup.timeframe}
                onChange={(event) => setSetup((current) => ({ ...current, timeframe: event.target.value }))}
                disabled={setupReadOnly || strategyDone || savingSetup || loading}
                className={inputClassName}
              >
                <option value="1D">1D</option>
                <option value="4H">4H</option>
                <option value="1W">1W</option>
              </select>
            </Field>
          </div>

          {!isTrade ? (
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <Field label={copy.dcaFrequencyLabel || "Frequency"}>
                <select value={setup.dcaFrequency} onChange={(event) => setSetup((current) => ({ ...current, dcaFrequency: event.target.value }))} disabled={setupReadOnly || savingSetup || loading} className={inputClassName}>
                  <option value="daily">{copy.dcaDaily || "Daily"}</option>
                  <option value="weekly">{copy.dcaWeekly || "Weekly"}</option>
                  <option value="monthly">{copy.dcaMonthly || "Monthly"}</option>
                </select>
              </Field>
              {setup.dcaFrequency === "weekly" ? (
                <Field label={copy.dcaWeekdayLabel || "Weekday"}>
                  <select value={setup.dcaDay} onChange={(event) => setSetup((current) => ({ ...current, dcaDay: event.target.value }))} disabled={setupReadOnly || savingSetup || loading} className={inputClassName}>
                    {DCA_WEEKDAYS.map((day) => (
                      <option key={day} value={day}>{copy.dcaWeekdays?.[day] || day}</option>
                    ))}
                  </select>
                </Field>
              ) : null}
              {setup.dcaFrequency === "monthly" ? (
                <Field label={copy.dcaMonthDayLabel || "Day of month"}>
                  <input type="number" min="1" max="28" step="1" value={setup.dcaMonthDay} onChange={(event) => setSetup((current) => ({ ...current, dcaMonthDay: event.target.value }))} disabled={setupReadOnly || savingSetup || loading} className={inputClassName} />
                </Field>
              ) : null}
            </div>
          ) : null}

          <div className="mt-8 border-t border-slate-200 pt-8">
            <MarketConditionPicker choice={conditionChoice} onChange={setConditionChoice} copy={t?.setups?.marketConditions} symbol={symbol} disabled={setupReadOnly || savingSetup || loading} allowOff={!isTrade || (setupDone && conditionChoice === "off")} isDca={!isTrade}>
              <div className="grid gap-3">
                  <div className="rounded-xl border border-slate-200 bg-white p-3">
                    <div className="mb-2 text-xs font-bold text-slate-700">{copy.benchmarkScoreLabel || "Jouw benchmarkscore"}</div>
                    <div className="grid grid-cols-2 gap-2">
                      {["min", "max"].map((bound) => (
                        <Field key={bound} label={bound === "min" ? copy.scoreMinLabel : copy.scoreMaxLabel}>
                          <input type="number" min="0" max="100" step="1"
                            value={setup[`${bound}_benchmark_score`]}
                            onChange={(event) => { setSetup((current) => ({ ...current, [`${bound}_benchmark_score`]: event.target.value })); setSetupScoreTouched(true); }}
                            disabled={setupReadOnly || savingSetup || loading} className={inputClassName} />
                        </Field>
                      ))}
                    </div>
                  </div>
              </div>
            </MarketConditionPicker>
          </div>

          {!setupDone ? (
            <div className="mt-5">
              <button
                type="button"
                onClick={handleSaveSetup}
                disabled={!setupValid || savingSetup || loading}
                className="inline-flex items-center justify-center rounded-2xl bg-blue-600 px-5 py-3 text-[11px] font-black uppercase tracking-[0.18em] text-white shadow-lg shadow-blue-500/20 transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {savingSetup ? copy.setupSaving || "Saving setup…" : copy.setupSave || "Save setup"}
              </button>
            </div>
          ) : editingSetup ? (
            <div className="mt-5 space-y-4">
              <p className="text-sm text-slate-600">{copy.savedPlanEditScope || "The trading pair and setup type stay the same. A linked strategy keeps its timeframe."}</p>
              {reviewingSetup ? (
                <div className="space-y-3 rounded-2xl border border-blue-200 bg-blue-50 p-4">
                  <p className="font-bold text-slate-900">{copy.reviewChanges || "Review your changes"}</p>
                  <SummaryRow label={copy.setupNameLabel || "Setup name"} value={setup.name.trim()} />
                  {!isTrade ? <SummaryRow label={copy.dcaFrequencyLabel || "Purchase schedule"} value={[
                    copy[`dca${setup.dcaFrequency?.[0]?.toUpperCase()}${setup.dcaFrequency?.slice(1)}`] || setup.dcaFrequency,
                    setup.dcaFrequency === "weekly" ? copy.dcaWeekdays?.[setup.dcaDay] : null,
                    setup.dcaFrequency === "monthly" ? setup.dcaMonthDay : null,
                  ].filter(Boolean).join(" · ")} /> : null}
                  <SummaryRow label={copy.scoreConditionLabel || "Score condition"} value={reviewConditionLabel} />
                  <p className="text-sm text-slate-700">{copy.setupUpdateImpact || "This updates the saved setup. A linked bot may use the new schedule and conditions at its next assessment; saving does not start a bot or place an order."}</p>
                  {linkedBots.length ? <p className="text-sm font-semibold text-amber-800">{copy.linkedBotImpact?.replace("{bots}", linkedBots.map((bot) => bot.name).join(", "))}</p> : null}
                  <div className="flex flex-wrap gap-3">
                    <button type="button" onClick={handleUpdateSetup} disabled={savingSetup} className="rounded-2xl bg-blue-600 px-5 py-3 text-sm font-bold text-white disabled:opacity-60">
                      {savingSetup ? copy.updating || "Updating…" : copy.confirmUpdate || "Update saved setup"}
                    </button>
                    <button type="button" onClick={() => setReviewingSetup(false)} disabled={savingSetup} className="rounded-2xl border border-slate-300 px-5 py-3 text-sm font-semibold text-slate-700">{copy.backToEdit || "Back to editing"}</button>
                  </div>
                </div>
              ) : (
                <div className="flex flex-wrap gap-3">
                  <button type="button" onClick={() => { setError(null); setReviewingSetup(true); }} disabled={!setupValid || !Object.keys(setupPatch).length || savingSetup} className="rounded-2xl bg-blue-600 px-5 py-3 text-sm font-bold text-white disabled:opacity-60">{copy.reviewChanges || "Review changes"}</button>
                  <button type="button" onClick={cancelSetupEdit} className="rounded-2xl border border-slate-300 px-5 py-3 text-sm font-semibold text-slate-700">{copy.cancelEdit || "Cancel"}</button>
                </div>
              )}
            </div>
          ) : (
            <div className="mt-5 grid gap-3 md:grid-cols-3">
              <SummaryRow label={copy.setupNameLabel || "Name"} value={setup.name.trim() || `${symbol} Setup`} />
              <SummaryRow
                label={copy.setupTypeLabel || "Type"}
                value={setup.setupType === "dca" ? copy.setupTypeDca || "DCA" : copy.setupTypeTrade || "Trade"}
              />
              <SummaryRow label={copy.setupTimeframeLabel || "Timeframe"} value={setup.timeframe} />
              {!isTrade ? (
                <SummaryRow
                  label={copy.dcaFrequencyLabel || "Frequency"}
                  value={[
                    copy[`dca${setup.dcaFrequency?.[0]?.toUpperCase()}${setup.dcaFrequency?.slice(1)}`] || setup.dcaFrequency,
                    setup.dcaFrequency === "weekly" ? (copy.dcaWeekdays?.[setup.dcaDay] || setup.dcaDay) : null,
                    setup.dcaFrequency === "monthly" ? setup.dcaMonthDay : null,
                  ].filter(Boolean).join(" · ")}
                />
              ) : null}
              <SummaryRow label={copy.scoreConditionLabel || "Score condition"} value={conditionLabel} />
              <button type="button" onClick={() => { setError(null); setEditingSetup(true); }} className="text-left text-sm font-semibold text-blue-700 underline-offset-2 hover:underline md:col-span-3">
                {copy.editSavedSetup || "Edit this setup"}
              </button>
            </div>
          )}
        </Section>

        <div ref={strategySectionRef}>
          <Section
            title={copy.strategyTitle || "2. Strategy"}
            subtitle={copy.strategySubtitle || "Link one strategy to the setup you just saved."}
            status={strategyDone}
            savedLabel={copy.savedLabel}
          >
            {!setupDone ? (
              <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-4 text-sm font-semibold text-amber-800">
                <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.18em] text-amber-700">
                  <Lock size={12} />
                  {copy.strategyLockedLabel || "Locked until setup is saved"}
                </div>
                <p className="mt-2">
                  {copy.strategyLockedBody || "Save the setup first. After that this strategy step opens immediately for the same asset."}
                </p>
              </div>
            ) : (
              <>
                <div className="grid gap-4 md:grid-cols-2">
                  <Field label={copy.strategyNameLabel || "Name"}>
                    <input
                      type="text"
                      value={strategy.name}
                      onChange={(event) => setStrategy((current) => ({ ...current, name: event.target.value }))}
                      placeholder={copy.strategyNamePlaceholder || `${symbol} Strategy`}
                      disabled={strategyReadOnly || savingStrategy || loading}
                      className={inputClassName}
                    />
                  </Field>

                  <Field label={scoreCurvePoints.length ? copy.strategyBaseAmountLabel : (isTrade ? copy.strategyAmountLabel : copy.strategyDcaAmountLabel)}>
                    <div className="relative">
                      <span aria-hidden="true" className="pointer-events-none absolute inset-y-0 left-4 flex items-center font-bold text-slate-700">€</span>
                      <input
                        type="number"
                        min="1"
                        step="1"
                        value={strategy.baseAmount}
                        onChange={(event) => setStrategy((current) => ({ ...current, baseAmount: event.target.value }))}
                        disabled={strategyReadOnly || savingStrategy || loading}
                        className={`${inputClassName} pl-10`}
                      />
                    </div>
                  </Field>
                </div>

                {scoreCurvePoints.length ? <p className="mt-3 text-sm text-slate-600">{scoreCurveTitle}: {scoreCurveDescription}{!scoreCurveIsStep ? ` ${copy.linearCurveNote}` : ""}</p> : null}

                {isTrade ? (
                  <div className="mt-4 grid gap-4 md:grid-cols-3">
                    <Field label={copy.strategyEntryLabel || "Entry"}>
                      <input
                        type="number"
                        step="0.01"
                        value={strategy.entry}
                        onChange={(event) => setStrategy((current) => ({ ...current, entry: event.target.value }))}
                        disabled={strategyReadOnly || savingStrategy || loading}
                        className={inputClassName}
                      />
                    </Field>

                    <Field label={copy.strategyTargetsLabel || "Targets"}>
                      <input
                        type="text"
                        value={strategy.targets}
                        onChange={(event) => setStrategy((current) => ({ ...current, targets: event.target.value }))}
                        placeholder={copy.strategyTargetsPlaceholder || "64500, 67000"}
                        disabled={strategyReadOnly || savingStrategy || loading}
                        className={inputClassName}
                      />
                    </Field>

                    <Field label={copy.strategyStopLabel || "Stop loss"}>
                      <input
                        type="number"
                        step="0.01"
                        value={strategy.stopLoss}
                        onChange={(event) => setStrategy((current) => ({ ...current, stopLoss: event.target.value }))}
                        disabled={strategyReadOnly || savingStrategy || loading}
                        className={inputClassName}
                      />
                    </Field>
                  </div>
                ) : null}

                {!strategyDone ? (
                  <div className="mt-5">
                    <div className="mb-5 space-y-2 rounded-2xl border border-blue-100 bg-blue-50 p-4 text-sm text-slate-800">
                      <p className="font-bold">{copy.strategyReviewBeforeSave}</p>
                      <p>{isTrade ? copy.strategyTradeExecutionSummary : copy.strategyDcaExecutionSummary
                        ?.replace("{amount}", String(strategy.baseAmount || "—"))
                        ?.replace("{cadence}", [
                          copy[`dca${setup.dcaFrequency?.[0]?.toUpperCase()}${setup.dcaFrequency?.slice(1)}`] || setup.dcaFrequency,
                          setup.dcaFrequency === "weekly" ? copy.dcaWeekdays?.[setup.dcaDay] : null,
                          setup.dcaFrequency === "monthly" ? setup.dcaMonthDay : null,
                        ].filter(Boolean).join(" · "))}</p>
                      <p>{isTrade ? copy.strategyTradeRiskSummary : copy.strategyDcaRiskSummary}</p>
                    </div>
                    <button
                      type="button"
                      onClick={handleSaveStrategy}
                      disabled={!setupDone || !strategyValid || savingStrategy || loading}
                      className="inline-flex items-center justify-center rounded-2xl bg-blue-600 px-5 py-3 text-[11px] font-black uppercase tracking-[0.18em] text-white shadow-lg shadow-blue-500/20 transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {savingStrategy ? copy.strategySaving || "Saving strategy…" : copy.strategySave || "Save strategy"}
                    </button>
                  </div>
                ) : editingStrategy ? (
                  <div className="mt-5 space-y-4">
                    {reviewingStrategy ? (
                      <div className="space-y-3 rounded-2xl border border-blue-200 bg-blue-50 p-4">
                        <p className="font-bold text-slate-900">{copy.reviewChanges || "Review your changes"}</p>
                        <SummaryRow label={copy.strategyNameLabel || "Name"} value={strategy.name.trim()} />
                        <SummaryRow label={scoreCurvePoints.length ? copy.strategyBaseAmountLabel || "Base amount (100%)" : (isTrade ? copy.strategyAmountLabel : copy.strategyDcaAmountLabel)} value={`€${strategy.baseAmount}`} />
                        {scoreCurvePoints.length ? <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800">
                          <p className="font-bold">{scoreCurveTitle}</p>
                          <p className="mt-1">{scoreCurveDescription}</p>
                          {!scoreCurveIsStep ? <p className="mt-1 text-slate-600">{copy.linearCurveNote}</p> : null}
                        </div> : null}
                        {isTrade ? <>
                          <SummaryRow label={copy.strategyEntryLabel || "Entry"} value={strategy.entry} />
                          <SummaryRow label={copy.strategyTargetsLabel || "Targets"} value={strategy.targets} />
                          <SummaryRow label={copy.strategyStopLabel || "Stop loss"} value={strategy.stopLoss} />
                        </> : null}
                        <p className="text-sm text-slate-700">{copy.strategyUpdateImpact || "This updates the saved strategy. A linked bot may use the new amount or risk levels at its next assessment; saving does not start a bot or place an order."}</p>
                        {linkedBots.length ? <p className="text-sm font-semibold text-amber-800">{copy.linkedBotImpact?.replace("{bots}", linkedBots.map((bot) => bot.name).join(", "))}</p> : null}
                        <div className="flex flex-wrap gap-3">
                          <button type="button" onClick={handleUpdateStrategy} disabled={savingStrategy} className="rounded-2xl bg-blue-600 px-5 py-3 text-sm font-bold text-white disabled:opacity-60">{savingStrategy ? copy.updating || "Updating…" : copy.confirmStrategyUpdate || "Update saved strategy"}</button>
                          <button type="button" onClick={() => setReviewingStrategy(false)} disabled={savingStrategy} className="rounded-2xl border border-slate-300 px-5 py-3 text-sm font-semibold text-slate-700">{copy.backToEdit || "Back to editing"}</button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex flex-wrap gap-3">
                        <button type="button" onClick={() => { setError(null); setReviewingStrategy(true); }} disabled={!strategyValid || !Object.keys(strategyPatch).length || savingStrategy} className="rounded-2xl bg-blue-600 px-5 py-3 text-sm font-bold text-white disabled:opacity-60">{copy.reviewChanges || "Review changes"}</button>
                        <button type="button" onClick={cancelStrategyEdit} className="rounded-2xl border border-slate-300 px-5 py-3 text-sm font-semibold text-slate-700">{copy.cancelEdit || "Cancel"}</button>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="mt-5 grid gap-3 md:grid-cols-2">
                    <SummaryRow
                      label={copy.strategyNameLabel || "Name"}
                      value={strategy.name.trim() || `${symbol} Strategy`}
                    />
                    <SummaryRow
                      label={scoreCurvePoints.length ? copy.strategyBaseAmountLabel : (isTrade ? copy.strategyAmountLabel : copy.strategyDcaAmountLabel)}
                      value={`€${String(strategy.baseAmount || "100")}`}
                    />
                    <button type="button" onClick={() => { setError(null); setEditingStrategy(true); }} className="text-left text-sm font-semibold text-blue-700 underline-offset-2 hover:underline md:col-span-2">{copy.editSavedStrategy || "Edit this strategy"}</button>
                  </div>
                )}
              </>
            )}
          </Section>
        </div>
      </div>

      {error ? (
        <div className="mt-6 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">
          {error}
        </div>
      ) : null}

      {setupDone ? (
        <section ref={completionSectionRef} className="mt-6 rounded-[28px] border border-emerald-200 bg-emerald-50 p-5 shadow-sm">
          <div className="flex flex-col gap-5 md:flex-row md:items-center md:justify-between">
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.18em] text-emerald-700">
                <CheckCircle2 size={14} />
                {copy.successEyebrow || "Plan ready"}
              </div>
              <h2 className="mt-2 text-2xl font-black tracking-tight text-slate-900">
                {strategyDone ? copy.successTitle || "Your setup and strategy are saved" : copy.optionalPlanTitle || "Je setup is opgeslagen"}
              </h2>
              <p className="mt-2 text-sm font-semibold leading-relaxed text-slate-600">
                {strategyDone ? copy.successMessage || "Review your plan, then continue when you are ready." : copy.optionalPlanBody || "Je kunt nu afronden. Een strategie en bot toevoegen kan later."}
              </p>
            </div>

            <button
              type="button"
              onClick={handleContinue}
              disabled={continuing || editingSetup || editingStrategy || savingSetup || savingStrategy}
              className="inline-flex items-center justify-center rounded-2xl bg-blue-600 px-5 py-3 text-[11px] font-black uppercase tracking-[0.18em] text-white shadow-lg shadow-blue-500/20 transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {continuing ? copy.continuingLabel || "Onboarding afronden…" : copy.finishWithoutAutomation || "Onboarding afronden"}
            </button>
          </div>

          <div className="mt-5 grid gap-3 md:grid-cols-3">
            <SummaryRow label={copy.assetLabel || "Asset"} value={symbol} />
            <SummaryRow
              label={copy.setupTitle || "1. Setup"}
              value={setup.name.trim() || `${symbol} Setup`}
            />
            <SummaryRow label={copy.strategyTitle || "2. Strategy"} value={strategyDone ? savedStrategy?.name || strategy.name.trim() : copy.optionalLater || "Later toevoegen"} />
          </div>
          {!strategyDone ? (
            <button type="button" onClick={() => strategySectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })} className="mt-4 block text-sm font-bold text-blue-700 underline-offset-2 hover:underline">
              {copy.optionalStrategyLink || "Optioneel: strategie toevoegen"}
            </button>
          ) : null}
          {strategyDone ? (
            <Link href={`/onboarding/automation?symbol=${encodeURIComponent(symbol)}&strategy_id=${encodeURIComponent(savedStrategy?.strategy_id ?? savedStrategy?.id ?? "")}`} className="mt-4 inline-block text-sm font-bold text-blue-700 underline-offset-2 hover:underline">
              {copy.optionalAutomationLink || "Optioneel: Paper-bot instellen"}
            </Link>
          ) : null}
        </section>
      ) : null}

      {!setupDone ? (
        <section className="mt-6 rounded-[28px] border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="text-[10px] font-black uppercase tracking-[0.18em] text-slate-400">
                {copy.nextStepLabel || "Next step"}
              </div>
              <p className="mt-2 text-sm font-semibold text-slate-700">
                {copy.nextStepSetup || "Save your setup to finish onboarding. You can add a strategy later."}
              </p>
            </div>
            <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-4 py-2 text-[11px] font-black uppercase tracking-[0.18em] text-slate-700">
              {copy.setupTitle || "1. Setup"}
              <ArrowRight size={13} />
            </div>
          </div>
        </section>
      ) : null}
    </div>
  );
}
