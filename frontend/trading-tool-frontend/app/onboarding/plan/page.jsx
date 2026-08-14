"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowRight, CheckCircle2, Lock, Sparkles } from "lucide-react";

import { useTranslation } from "@/app/providers/I18nProvider";
import OnboardingBanner from "@/components/onboarding/OnboardingBanner";
import { useOnboarding } from "@/hooks/useOnboarding";
import { fetchActiveSetup, fetchLastSetup, saveNewSetup } from "@/lib/api/setups";
import { createStrategy, fetchLastStrategy, fetchStrategyBySetup } from "@/lib/api/strategy";

const DEFAULT_SETUP = {
  name: "",
  setupType: "trade",
  timeframe: "4H",
};

const DEFAULT_STRATEGY = {
  name: "",
  executionMode: "fixed",
  baseAmount: "100",
  entry: "",
  targets: "",
  stopLoss: "",
};

function Section({ title, subtitle, children, status }) {
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
            Saved
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

function Field({ label, children }) {
  return (
    <label className="block space-y-2">
      <span className="text-[10px] font-black uppercase tracking-[0.18em] text-slate-400">{label}</span>
      {children}
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

  const symbol = useMemo(
    () => String(searchParams.get("symbol") || status?.active_asset || "BTC").toUpperCase(),
    [searchParams, status?.active_asset],
  );

  const copy = t?.traderProfile?.planOnboardingStep || {};

  const [loading, setLoading] = useState(true);
  const [continuing, setContinuing] = useState(false);
  const [savingSetup, setSavingSetup] = useState(false);
  const [savingStrategy, setSavingStrategy] = useState(false);
  const [error, setError] = useState(null);

  const [setup, setSetup] = useState(DEFAULT_SETUP);
  const [strategy, setStrategy] = useState(DEFAULT_STRATEGY);
  const [savedSetup, setSavedSetup] = useState(null);
  const [savedStrategy, setSavedStrategy] = useState(null);

  useEffect(() => {
    let cancelled = false;

    async function loadExisting() {
      try {
        setLoading(true);
        setError(null);

        const [activeSetup, lastSetup, lastStrategy] = await Promise.all([
          fetchActiveSetup(symbol).catch(() => null),
          fetchLastSetup().catch(() => null),
          fetchLastStrategy().catch(() => null),
        ]);

        if (cancelled) return;

        const setupCandidate =
          activeSetup?.symbol === symbol
            ? activeSetup
            : lastSetup?.symbol === symbol
              ? lastSetup
              : null;

        if (setupCandidate) {
          setSavedSetup(setupCandidate);
          setSetup({
            name: setupCandidate.name || `${symbol} Setup`,
            setupType: String(setupCandidate.setup_type || "trade").toLowerCase(),
            timeframe: setupCandidate.timeframe || "4H",
          });

          const bySetup = await fetchStrategyBySetup(setupCandidate.id).catch(() => null);
          if (!cancelled && bySetup) {
            setSavedStrategy(bySetup);
            setStrategy({
              name: bySetup.name || `${symbol} Strategy`,
              executionMode: bySetup.execution_mode || "fixed",
              baseAmount: String(bySetup.base_amount || bySetup.amount || 100),
              entry: bySetup.entry != null ? String(bySetup.entry) : "",
              targets: Array.isArray(bySetup.targets)
                ? bySetup.targets
                    .map((item) => (typeof item === "object" ? item.price : item))
                    .join(", ")
                : "",
              stopLoss: bySetup.stop_loss != null ? String(bySetup.stop_loss) : "",
            });
          } else if (!cancelled && lastStrategy?.strategy?.setup_id === setupCandidate.id) {
            setSavedStrategy(lastStrategy.strategy);
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
  }, [copy.loadError, symbol]);

  const setupDone = Boolean(status?.has_setup || savedSetup);
  const strategyDone = Boolean(status?.has_strategy || savedStrategy);
  const allDone = setupDone && strategyDone;
  const isTrade = String(setup.setupType || "").toLowerCase() === "trade";

  const setupValid = Boolean(setup.name.trim() && setup.setupType && setup.timeframe);
  const strategyValid = Boolean(
    strategy.name.trim() &&
      Number(strategy.baseAmount) > 0 &&
      (!isTrade || (strategy.entry.trim() && strategy.targets.trim() && strategy.stopLoss.trim())),
  );

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
        setup_type: setup.setupType,
        timeframe: setup.timeframe,
        min_macro_score: 30,
        max_macro_score: 70,
        min_technical_score: 40,
        max_technical_score: 80,
        min_market_score: 20,
        max_market_score: 60,
      });

      const nextSetup = response?.setup ?? response ?? null;
      setSavedSetup(nextSetup);

      if (!status?.has_setup) {
        await completeStep("setup");
      }

      window.setTimeout(() => {
        strategySectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 150);
    } catch (err) {
      console.error("Failed to save onboarding setup", err);
      setError(copy.setupSaveError || "Saving the setup failed. Try again.");
    } finally {
      setSavingSetup(false);
    }
  };

  const handleSaveStrategy = async () => {
    if (!savedSetup) {
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
        setup_id: Number(savedSetup.id),
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
      setSavedStrategy(response?.strategy ?? response ?? payload);

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
    setContinuing(true);
    router.push(`/bot?onboarding=1&step=bot&symbol=${encodeURIComponent(symbol)}`);
  };

  const reviewReady = setupDone && strategyDone;

  return (
    <div className="mx-auto max-w-5xl py-8">
      <OnboardingBanner step="setup" />

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
        >
          <div className="grid gap-4 md:grid-cols-3">
            <Field label={copy.setupNameLabel || "Name"}>
              <input
                type="text"
                value={setup.name}
                onChange={(event) => setSetup((current) => ({ ...current, name: event.target.value }))}
                placeholder={copy.setupNamePlaceholder || `${symbol} Setup`}
                disabled={setupDone || savingSetup || loading}
                className={inputClassName}
              />
            </Field>

            <Field label={copy.setupTypeLabel || "Type"}>
              <select
                value={setup.setupType}
                onChange={(event) => setSetup((current) => ({ ...current, setupType: event.target.value }))}
                disabled={setupDone || savingSetup || loading}
                className={inputClassName}
              >
                <option value="trade">{copy.setupTypeTrade || "Trade"}</option>
                <option value="dca">{copy.setupTypeDca || "DCA"}</option>
              </select>
            </Field>

            <Field label={copy.setupTimeframeLabel || "Timeframe"}>
              <select
                value={setup.timeframe}
                onChange={(event) => setSetup((current) => ({ ...current, timeframe: event.target.value }))}
                disabled={setupDone || savingSetup || loading}
                className={inputClassName}
              >
                <option value="1D">1D</option>
                <option value="4H">4H</option>
                <option value="1W">1W</option>
              </select>
            </Field>
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
          ) : (
            <div className="mt-5 grid gap-3 md:grid-cols-3">
              <SummaryRow label={copy.setupNameLabel || "Name"} value={setup.name.trim() || `${symbol} Setup`} />
              <SummaryRow
                label={copy.setupTypeLabel || "Type"}
                value={setup.setupType === "dca" ? copy.setupTypeDca || "DCA" : copy.setupTypeTrade || "Trade"}
              />
              <SummaryRow label={copy.setupTimeframeLabel || "Timeframe"} value={setup.timeframe} />
            </div>
          )}
        </Section>

        <div ref={strategySectionRef}>
          <Section
            title={copy.strategyTitle || "2. Strategy"}
            subtitle={copy.strategySubtitle || "Link one strategy to the setup you just saved."}
            status={strategyDone}
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
                      disabled={strategyDone || savingStrategy || loading}
                      className={inputClassName}
                    />
                  </Field>

                  <Field label={copy.strategyAmountLabel || "Base amount"}>
                    <input
                      type="number"
                      min="1"
                      step="1"
                      value={strategy.baseAmount}
                      onChange={(event) => setStrategy((current) => ({ ...current, baseAmount: event.target.value }))}
                      disabled={strategyDone || savingStrategy || loading}
                      className={inputClassName}
                    />
                  </Field>
                </div>

                {isTrade ? (
                  <div className="mt-4 grid gap-4 md:grid-cols-3">
                    <Field label={copy.strategyEntryLabel || "Entry"}>
                      <input
                        type="number"
                        step="0.01"
                        value={strategy.entry}
                        onChange={(event) => setStrategy((current) => ({ ...current, entry: event.target.value }))}
                        disabled={strategyDone || savingStrategy || loading}
                        className={inputClassName}
                      />
                    </Field>

                    <Field label={copy.strategyTargetsLabel || "Targets"}>
                      <input
                        type="text"
                        value={strategy.targets}
                        onChange={(event) => setStrategy((current) => ({ ...current, targets: event.target.value }))}
                        placeholder={copy.strategyTargetsPlaceholder || "64500, 67000"}
                        disabled={strategyDone || savingStrategy || loading}
                        className={inputClassName}
                      />
                    </Field>

                    <Field label={copy.strategyStopLabel || "Stop loss"}>
                      <input
                        type="number"
                        step="0.01"
                        value={strategy.stopLoss}
                        onChange={(event) => setStrategy((current) => ({ ...current, stopLoss: event.target.value }))}
                        disabled={strategyDone || savingStrategy || loading}
                        className={inputClassName}
                      />
                    </Field>
                  </div>
                ) : null}

                {!strategyDone ? (
                  <div className="mt-5">
                    <button
                      type="button"
                      onClick={handleSaveStrategy}
                      disabled={!savedSetup || !strategyValid || savingStrategy || loading}
                      className="inline-flex items-center justify-center rounded-2xl bg-blue-600 px-5 py-3 text-[11px] font-black uppercase tracking-[0.18em] text-white shadow-lg shadow-blue-500/20 transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {savingStrategy ? copy.strategySaving || "Saving strategy…" : copy.strategySave || "Save strategy"}
                    </button>
                  </div>
                ) : (
                  <div className="mt-5 grid gap-3 md:grid-cols-2">
                    <SummaryRow
                      label={copy.strategyNameLabel || "Name"}
                      value={strategy.name.trim() || `${symbol} Strategy`}
                    />
                    <SummaryRow
                      label={copy.strategyAmountLabel || "Base amount"}
                      value={String(strategy.baseAmount || "100")}
                    />
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

      {allDone ? (
        <section className="mt-6 rounded-[28px] border border-emerald-200 bg-emerald-50 p-5 shadow-sm">
          <div className="flex flex-col gap-5 md:flex-row md:items-center md:justify-between">
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.18em] text-emerald-700">
                <CheckCircle2 size={14} />
                {copy.successEyebrow || "Plan ready"}
              </div>
              <h2 className="mt-2 text-2xl font-black tracking-tight text-slate-900">
                {copy.successTitle || "Your first setup and strategy are saved"}
              </h2>
              <p className="mt-2 text-sm font-semibold leading-relaxed text-slate-600">
                {copy.successMessage || "Review your first plan briefly, then continue to Automation when you are ready."}
              </p>
            </div>

            <button
              type="button"
              onClick={handleContinue}
              disabled={continuing}
              className="inline-flex items-center justify-center rounded-2xl bg-blue-600 px-5 py-3 text-[11px] font-black uppercase tracking-[0.18em] text-white shadow-lg shadow-blue-500/20 transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {continuing ? copy.continuingLabel || "Opening Automation…" : copy.continueLabel || "Continue to Automation"}
            </button>
          </div>

          <div className="mt-5 grid gap-3 md:grid-cols-3">
            <SummaryRow label={copy.assetLabel || "Asset"} value={symbol} />
            <SummaryRow
              label={copy.setupTitle || "1. Setup"}
              value={setup.name.trim() || `${symbol} Setup`}
            />
            <SummaryRow
              label={copy.strategyTitle || "2. Strategy"}
              value={strategy.name.trim() || `${symbol} Strategy`}
            />
          </div>
        </section>
      ) : null}

      {!allDone ? (
        <section className="mt-6 rounded-[28px] border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="text-[10px] font-black uppercase tracking-[0.18em] text-slate-400">
                {copy.nextStepLabel || "Next step"}
              </div>
              <p className="mt-2 text-sm font-semibold text-slate-700">
                {setupDone
                  ? copy.nextStepStrategy || "Save one strategy for this setup. Then Automation opens automatically."
                  : copy.nextStepSetup || "Start by saving one setup. After that the strategy step unlocks immediately."}
              </p>
            </div>
            <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-4 py-2 text-[11px] font-black uppercase tracking-[0.18em] text-slate-700">
              {setupDone ? (copy.strategyTitle || "2. Strategy") : (copy.setupTitle || "1. Setup")}
              <ArrowRight size={13} />
            </div>
          </div>
        </section>
      ) : null}
    </div>
  );
}
