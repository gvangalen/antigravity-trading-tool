"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Check, Sparkles, User } from "lucide-react";
import { useTranslation } from "@/app/providers/I18nProvider";
import OnboardingBanner from "@/components/onboarding/OnboardingBanner";
import { useOnboarding } from "@/hooks/useOnboarding";
import { getAssistantPreferences, updateAssistantPreferences } from "@/lib/api/ai";
import {
  getAssetFocusOptions,
  getBehaviorFlagOptions,
  getExperienceLevelOptions,
  getGoalOptions,
  getRiskProfileOptions,
  getTimeframeOptions,
  getTraderTypeOptions,
  normalizeTraderProfilePreferences,
  serializeTraderProfilePreferences,
} from "@/lib/traderProfileOptions";

function MultiChoiceGroup({ title, subtitle, options, values, onToggle }) {
  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="mb-4">
        <h3 className="text-lg font-black tracking-tight text-slate-900">{title}</h3>
        <p className="mt-1 text-sm font-medium leading-relaxed text-slate-500">{subtitle}</p>
      </div>
      <div className="flex flex-wrap gap-3">
        {options.map((option) => {
          const active = values.includes(option.value);
          return (
            <button
              key={option.value}
              type="button"
              onClick={() => onToggle(option.value)}
              className={`inline-flex items-center gap-2 rounded-2xl border px-4 py-3 text-sm font-bold transition ${
                active
                  ? "border-blue-600 bg-blue-600 text-white shadow-lg shadow-blue-500/20"
                  : "border-slate-200 bg-slate-50 text-slate-700 hover:border-blue-200 hover:bg-white"
              }`}
            >
              {active ? <Check size={14} /> : null}
              {option.label}
            </button>
          );
        })}
      </div>
    </section>
  );
}

export default function OnboardingProfilePage() {
  const router = useRouter();
  const { t } = useTranslation();
  const { completeStep, saving } = useOnboarding();
  const [loadingPrefs, setLoadingPrefs] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [form, setForm] = useState({
    trader_types: [],
    primary_timeframes: [],
    asset_focus: [],
    investment_goals_list: [],
    experience_levels: [],
    risk_profiles: [],
    behavior_flags: [],
  });

  useEffect(() => {
    let cancelled = false;

    async function loadPreferences() {
      try {
        setLoadingPrefs(true);
        const response = await getAssistantPreferences();
        const preferences = response?.preferences || {};
        if (cancelled) return;

        setForm(normalizeTraderProfilePreferences(preferences));
      } catch (err) {
        console.error("Profielvoorkeuren laden mislukt", err);
      } finally {
        if (!cancelled) {
          setLoadingPrefs(false);
        }
      }
    }

    loadPreferences();
    return () => {
      cancelled = true;
    };
  }, []);

  const isValid = useMemo(() => {
    return (
      form.trader_types.length > 0 &&
      form.primary_timeframes.length > 0 &&
      form.asset_focus.length > 0 &&
      form.investment_goals_list.length > 0 &&
      form.experience_levels.length > 0 &&
      form.risk_profiles.length > 0
    );
  }, [form]);

  const traderTypeOptions = useMemo(() => getTraderTypeOptions(t), [t]);
  const timeframeOptions = useMemo(() => getTimeframeOptions(t), [t]);
  const assetFocusOptions = useMemo(() => getAssetFocusOptions(t), [t]);
  const goalOptions = useMemo(() => getGoalOptions(t), [t]);
  const experienceOptions = useMemo(() => getExperienceLevelOptions(t), [t]);
  const riskOptions = useMemo(() => getRiskProfileOptions(t), [t]);
  const behaviorOptions = useMemo(() => getBehaviorFlagOptions(t), [t]);

  const toggleMulti = (field, value) => {
    setForm((current) => {
      const list = current[field];
      const nextList = list.includes(value)
        ? list.filter((item) => item !== value)
        : [...list, value];

      return {
        ...current,
        [field]: nextList,
      };
    });
  };

  const handleSubmit = async () => {
    if (!isValid) {
      setError(t?.traderProfile?.onboardingStep?.validationError);
      return;
    }

    try {
      setSubmitting(true);
      setError(null);

      await updateAssistantPreferences(serializeTraderProfilePreferences(form));
      await completeStep("profile");
      router.push("/onboarding");
    } catch (err) {
      console.error("Profiel opslaan mislukt", err);
      setError(t?.traderProfile?.onboardingStep?.saveError);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-5xl py-8">
      <OnboardingBanner step="profile" />

      <div className="mb-10 rounded-3xl border border-slate-200 bg-white p-8 shadow-sm">
        <div className="flex flex-col gap-6 md:flex-row md:items-start md:justify-between">
          <div className="max-w-2xl">
            <div className="mb-3 flex items-center gap-3">
              <div className="rounded-2xl bg-blue-50 p-4 text-blue-600">
                <User className="h-6 w-6" />
              </div>
              <div>
                <div className="text-[10px] font-black uppercase tracking-[0.25em] text-blue-600">
                  {t?.traderProfile?.onboardingStep?.stepNumber}
                </div>
                <h1 className="text-3xl font-black tracking-tight text-slate-900">
                  {t?.traderProfile?.onboardingStep?.title}
                </h1>
              </div>
            </div>
            <p className="text-sm font-medium leading-relaxed text-slate-500">
              {t?.traderProfile?.onboardingStep?.description}
            </p>
          </div>

          <div className="rounded-2xl border border-blue-100 bg-blue-50 px-4 py-3 text-sm font-semibold leading-relaxed text-slate-700">
            <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-blue-600">
              <Sparkles size={14} />
              {t?.traderProfile?.onboardingStep?.finnSaysLabel}
            </div>
            <p className="mt-2 max-w-sm">
              {t?.traderProfile?.onboardingStep?.finnSaysBody}
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6">
        <MultiChoiceGroup
          title={t?.traderProfile?.groups?.traderTypes?.title}
          subtitle={t?.traderProfile?.groups?.traderTypes?.subtitle}
          options={traderTypeOptions}
          values={form.trader_types}
          onToggle={(value) => toggleMulti("trader_types", value)}
        />

        <MultiChoiceGroup
          title={t?.traderProfile?.groups?.timeframes?.title}
          subtitle={t?.traderProfile?.groups?.timeframes?.subtitle}
          options={timeframeOptions}
          values={form.primary_timeframes}
          onToggle={(value) => toggleMulti("primary_timeframes", value)}
        />

        <MultiChoiceGroup
          title={t?.traderProfile?.groups?.assetFocus?.title}
          subtitle={t?.traderProfile?.groups?.assetFocus?.subtitle}
          options={assetFocusOptions}
          values={form.asset_focus}
          onToggle={(value) => toggleMulti("asset_focus", value)}
        />

        <MultiChoiceGroup
          title={t?.traderProfile?.groups?.goals?.title}
          subtitle={t?.traderProfile?.groups?.goals?.subtitle}
          options={goalOptions}
          values={form.investment_goals_list}
          onToggle={(value) => toggleMulti("investment_goals_list", value)}
        />

        <MultiChoiceGroup
          title={t?.traderProfile?.groups?.experience?.title}
          subtitle={t?.traderProfile?.groups?.experience?.subtitle}
          options={experienceOptions}
          values={form.experience_levels}
          onToggle={(value) => toggleMulti("experience_levels", value)}
        />

        <MultiChoiceGroup
          title={t?.traderProfile?.groups?.risk?.title}
          subtitle={t?.traderProfile?.groups?.risk?.subtitle}
          options={riskOptions}
          values={form.risk_profiles}
          onToggle={(value) => toggleMulti("risk_profiles", value)}
        />

        <MultiChoiceGroup
          title={t?.traderProfile?.groups?.behavior?.title}
          subtitle={t?.traderProfile?.groups?.behavior?.subtitle}
          options={behaviorOptions}
          values={form.behavior_flags}
          onToggle={(value) => toggleMulti("behavior_flags", value)}
        />
      </div>

      {error ? (
        <div className="mt-6 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">
          {error}
        </div>
      ) : null}

      <div className="mt-8 flex flex-col gap-4 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm md:flex-row md:items-center md:justify-between">
        <p className="text-sm font-medium leading-relaxed text-slate-500">
          {t?.traderProfile?.onboardingStep?.footer}
        </p>
        <button
          type="button"
          onClick={handleSubmit}
          disabled={!isValid || loadingPrefs || saving || submitting}
          className="inline-flex items-center justify-center gap-2 rounded-2xl bg-blue-600 px-5 py-3 text-[11px] font-black uppercase tracking-[0.18em] text-white shadow-lg shadow-blue-500/20 transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting || saving
            ? t?.traderProfile?.onboardingStep?.saving
            : t?.traderProfile?.onboardingStep?.saveAndContinue}
          <ArrowRight size={14} />
        </button>
      </div>
    </div>
  );
}
