"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Check, Sparkles, User } from "lucide-react";
import OnboardingBanner from "@/components/onboarding/OnboardingBanner";
import { useOnboarding } from "@/hooks/useOnboarding";
import { getAssistantPreferences, updateAssistantPreferences } from "@/lib/api/ai";
import {
  ASSET_FOCUS,
  EXPERIENCE_LEVELS,
  GOALS,
  normalizeTraderProfilePreferences,
  RISK_PROFILES,
  serializeTraderProfilePreferences,
  TIMEFRAMES,
  TRADER_TYPES,
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
      setError("Vul eerst alle profielvelden in zodat Finn je goed kan begeleiden.");
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
      setError("Opslaan van je traderprofiel is mislukt. Probeer het nog eens.");
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
                  Stap 1 van 6
                </div>
                <h1 className="text-3xl font-black tracking-tight text-slate-900">
                  Wie ben jij als trader?
                </h1>
              </div>
            </div>
            <p className="text-sm font-medium leading-relaxed text-slate-500">
              Finn gebruikt dit profiel om uitleg, waarschuwingen en setupbegeleiding meteen beter
              af te stemmen op jouw stijl. Zo krijg je minder ruis en relevanter advies.
            </p>
          </div>

          <div className="rounded-2xl border border-blue-100 bg-blue-50 px-4 py-3 text-sm font-semibold leading-relaxed text-slate-700">
            <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-blue-600">
              <Sparkles size={14} />
              Finn zegt
            </div>
            <p className="mt-2 max-w-sm">
              Eerst jij, dan pas de markt. Met jouw profiel kan Finn beter bepalen welke signalen,
              timeframes en waarschuwingen echt relevant zijn.
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6">
        <MultiChoiceGroup
          title="Wat voor trader ben je?"
          subtitle="Kies een of meer stijlen die passen bij hoe jij normaal handelt of investeert."
          options={TRADER_TYPES}
          values={form.trader_types}
          onToggle={(value) => toggleMulti("trader_types", value)}
        />

        <MultiChoiceGroup
          title="Welke timeframes gebruik je?"
          subtitle="Je kunt meerdere selecteren. Finn gebruikt dit om irrelevante signalen te dempen."
          options={TIMEFRAMES}
          values={form.primary_timeframes}
          onToggle={(value) => toggleMulti("primary_timeframes", value)}
        />

        <MultiChoiceGroup
          title="Waar focus je op?"
          subtitle="Kies de markten of assets waar Finn in je context vooral rekening mee moet houden."
          options={ASSET_FOCUS}
          values={form.asset_focus}
          onToggle={(value) => toggleMulti("asset_focus", value)}
        />

        <MultiChoiceGroup
          title="Wat is je doel?"
          subtitle="Kies een of meer doelen. Finn gebruikt dit om coaching en waarschuwingen op jouw intentie af te stemmen."
          options={GOALS}
          values={form.investment_goals_list}
          onToggle={(value) => toggleMulti("investment_goals_list", value)}
        />

        <MultiChoiceGroup
          title="Hoeveel ervaring heb je?"
          subtitle="Kies wat nu het best bij je past. Je kunt meerdere lagen aanvinken als je tussen niveaus in zit."
          options={EXPERIENCE_LEVELS}
          values={form.experience_levels}
          onToggle={(value) => toggleMulti("experience_levels", value)}
        />

        <MultiChoiceGroup
          title="Wat is je risicoprofiel?"
          subtitle="Zo kan Finn beter kiezen tussen remmen, waarschuwen of juist ruimte geven. Je kunt combineren als je per context verschilt."
          options={RISK_PROFILES}
          values={form.risk_profiles}
          onToggle={(value) => toggleMulti("risk_profiles", value)}
        />
      </div>

      {error ? (
        <div className="mt-6 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">
          {error}
        </div>
      ) : null}

      <div className="mt-8 flex flex-col gap-4 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm md:flex-row md:items-center md:justify-between">
        <p className="text-sm font-medium leading-relaxed text-slate-500">
          Sla je profiel op om de rest van je onboarding persoonlijker te maken. Daarna ontgrendel
          je de markt- en setupstappen met veel minder ruis.
        </p>
        <button
          type="button"
          onClick={handleSubmit}
          disabled={!isValid || loadingPrefs || saving || submitting}
          className="inline-flex items-center justify-center gap-2 rounded-2xl bg-blue-600 px-5 py-3 text-[11px] font-black uppercase tracking-[0.18em] text-white shadow-lg shadow-blue-500/20 transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting || saving ? "Profiel opslaan..." : "Profiel opslaan en doorgaan"}
          <ArrowRight size={14} />
        </button>
      </div>
    </div>
  );
}
