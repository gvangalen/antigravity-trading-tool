"use client";

import { useAuth } from "@/components/auth/AuthProvider";
import { getAssistantPreferences, updateAssistantPreferences } from "@/lib/api/ai";
import {
  ASSET_FOCUS,
  createOptionLabelMap,
  EXPERIENCE_LEVELS,
  GOALS,
  normalizeTraderProfilePreferences,
  RISK_PROFILES,
  serializeTraderProfilePreferences,
  TIMEFRAMES,
  TRADER_TYPES,
} from "@/lib/traderProfileOptions";
import { User, Mail, Shield, ArrowUpRight, Brain, LogOut, Loader2, Sparkles, Pencil, Save } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useModal } from "@/components/modal/ModalProvider";

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
              {option.label}
            </button>
          );
        })}
      </div>
    </section>
  );
}

export default function ProfilePage() {
  const { user, logout } = useAuth();
  const { showSnackbar } = useModal();
  const router = useRouter();
  const [loadingLogout, setLoadingLogout] = useState(false);
  const [loadingPreferences, setLoadingPreferences] = useState(true);
  const [savingProfile, setSavingProfile] = useState(false);
  const [editingProfile, setEditingProfile] = useState(false);
  const [profileError, setProfileError] = useState(null);
  const [profileForm, setProfileForm] = useState({
    trader_types: [],
    primary_timeframes: [],
    asset_focus: [],
    investment_goals_list: [],
    experience_levels: [],
    risk_profiles: [],
  });

  if (!user) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
      </div>
    );
  }

  const handleLogout = async () => {
    setLoadingLogout(true);
    await logout();
    showSnackbar("You have been safely logged out ✔", "success");
    router.push("/login");
  };

  const fullName = `${user.first_name || ""} ${user.last_name || ""}`.trim() || user.email;
  const requestsUsed = user.ai_requests_used_day || 0;
  const requestsLimit = user.ai_requests_limit_day || 25;
  const usagePct = Math.min((requestsUsed / requestsLimit) * 100, 100);
  const traderTypeMap = useMemo(() => createOptionLabelMap(TRADER_TYPES), []);
  const timeframeMap = useMemo(() => createOptionLabelMap(TIMEFRAMES), []);
  const assetFocusMap = useMemo(() => createOptionLabelMap(ASSET_FOCUS), []);
  const goalsMap = useMemo(() => createOptionLabelMap(GOALS), []);
  const experienceMap = useMemo(() => createOptionLabelMap(EXPERIENCE_LEVELS), []);
  const riskMap = useMemo(() => createOptionLabelMap(RISK_PROFILES), []);

  useEffect(() => {
    let cancelled = false;

    async function loadPreferences() {
      try {
        setLoadingPreferences(true);
        const response = await getAssistantPreferences();
        const preferences = response?.preferences || {};
        if (cancelled) return;

        setProfileForm(normalizeTraderProfilePreferences(preferences));
      } catch (err) {
        console.error("Traderprofiel laden mislukt", err);
        if (!cancelled) {
          setProfileError("Het traderprofiel kon niet geladen worden.");
        }
      } finally {
        if (!cancelled) {
          setLoadingPreferences(false);
        }
      }
    }

    loadPreferences();
    return () => {
      cancelled = true;
    };
  }, []);

  const hasCompleteProfile = useMemo(() => {
    return (
      profileForm.trader_types.length > 0 &&
      profileForm.primary_timeframes.length > 0 &&
      profileForm.asset_focus.length > 0 &&
      profileForm.investment_goals_list.length > 0 &&
      profileForm.experience_levels.length > 0 &&
      profileForm.risk_profiles.length > 0
    );
  }, [profileForm]);

  const toggleMulti = (field, value) => {
    setProfileForm((current) => {
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

  const handleSaveProfile = async () => {
    if (!hasCompleteProfile) {
      setProfileError("Vul eerst alle traderprofielvelden in zodat Finn je goed kan begeleiden.");
      return;
    }

    try {
      setSavingProfile(true);
      setProfileError(null);
      await updateAssistantPreferences(serializeTraderProfilePreferences(profileForm));
      setEditingProfile(false);
      showSnackbar("Tradingprofiel opgeslagen", "success");
    } catch (err) {
      console.error("Traderprofiel opslaan mislukt", err);
      setProfileError("Opslaan van je traderprofiel is mislukt. Probeer het nog eens.");
    } finally {
      setSavingProfile(false);
    }
  };

  const summaryChips = [
    ...profileForm.trader_types.map((value) => traderTypeMap[value]).filter(Boolean),
    ...profileForm.investment_goals_list.map((value) => goalsMap[value]).filter(Boolean),
    ...profileForm.experience_levels.map((value) => experienceMap[value]).filter(Boolean),
    ...profileForm.risk_profiles.map((value) => riskMap[value]).filter(Boolean),
  ].filter(Boolean);

  return (
    <div className="min-h-screen bg-background text-foreground transition-colors duration-300 p-8 pt-12">
      <div className="max-w-4xl mx-auto space-y-8 animate-fade-in">
        {/* HEADER */}
        <div className="border-l-4 border-blue-600 pl-8 mb-12">
          <div className="text-[11px] font-black text-blue-600 uppercase tracking-[0.3em] mb-2 opacity-80">
            Account Laboratory
          </div>
          <h1 className="text-5xl font-black text-foreground tracking-tight leading-none">
            User Profile
          </h1>
        </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        
        {/* 1. USER INFO BLOK */}
        <div className="bg-card border-2 border-[var(--color-border)] rounded-[2.5rem] p-10 flex flex-col justify-between transition-all hover:border-blue-600/20 group">
          <div className="space-y-8">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-2xl bg-blue-600 text-white flex items-center justify-center font-black text-xl shadow-lg shadow-blue-900/20">
                {fullName.charAt(0).toUpperCase()}
              </div>
              <div>
                <div className="text-[10px] font-black text-secondary uppercase tracking-widest mb-1">Trader Identity</div>
                <div className="text-2xl font-black text-foreground tracking-tight">{fullName}</div>
              </div>
            </div>

            <div className="space-y-6">
              <div className="flex items-center gap-4">
                <div className="p-2.5 rounded-xl bg-[var(--color-border-subtle)] text-secondary">
                  <Mail size={18} />
                </div>
                <div>
                  <div className="text-[9px] font-black text-dim uppercase tracking-widest mb-0.5">Contact Port</div>
                  <div className="text-sm font-bold text-foreground">{user.email}</div>
                </div>
              </div>

              <div className="flex items-center gap-4">
                <div className="p-2.5 rounded-xl bg-[var(--color-border-subtle)] text-secondary">
                  <Shield size={18} />
                </div>
                <div>
                  <div className="text-[9px] font-black text-dim uppercase tracking-widest mb-0.5">Authorization Level</div>
                  <div className="inline-flex items-center px-2 py-0.5 rounded-md bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 text-[10px] font-black uppercase tracking-tighter border border-blue-200 dark:border-blue-800">
                    {user.role || 'PRO'}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* 2. SUBSCRIPTION BLOK */}
        <div className="bg-card border-2 border-[var(--color-border)] rounded-[2.5rem] p-10 flex flex-col justify-between transition-all hover:border-blue-600/20 group relative overflow-hidden">
          {/* Subtle Accent Background */}
          <div className="absolute top-0 right-0 w-32 h-32 bg-blue-600/5 blur-3xl rounded-full -mr-16 -mt-16 group-hover:scale-150 transition-transform duration-1000" />
          
          <div className="relative z-10 space-y-12">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-[10px] font-black text-secondary uppercase tracking-widest mb-1">Service Tier</div>
                <div className="text-3xl font-black text-foreground tracking-tighter uppercase italic">
                  {user.ai_plan || 'Basis'} Plan
                </div>
              </div>
              <div className="px-3 py-1 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-500 text-[9px] font-black uppercase tracking-widest flex items-center gap-1.5">
                <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                Active
              </div>
            </div>

            <div className="py-6 border-y border-[var(--color-border-subtle)]">
               <p className="text-[11px] font-bold text-dim leading-relaxed uppercase tracking-widest">
                 Professional access enabled. All intelligence nodes are fully synchronized with your account.
               </p>
            </div>

            <button className="w-full bg-foreground text-card hover:bg-slate-800 py-4 rounded-2xl text-[11px] font-black uppercase tracking-widest transition-all flex items-center justify-center gap-2 group/btn active:scale-95 shadow-xl">
              Upgrade to Pro Level
              <ArrowUpRight size={14} className="group-hover/btn:translate-x-0.5 group-hover/btn:-translate-y-0.5 transition-transform" />
            </button>
          </div>
        </div>

      </div>

      <div className="bg-card border-2 border-[var(--color-border)] rounded-[2.5rem] p-10 space-y-8">
        <div className="flex flex-col gap-6 md:flex-row md:items-start md:justify-between">
          <div className="max-w-2xl">
            <div className="mb-3 flex items-center gap-3">
              <div className="rounded-2xl bg-blue-50 p-4 text-blue-600">
                <Sparkles className="h-6 w-6" />
              </div>
              <div>
                <div className="text-[10px] font-black uppercase tracking-[0.25em] text-blue-600">
                  Tradingprofiel
                </div>
                <h2 className="text-3xl font-black tracking-tight text-slate-900">
                  Finn leert hier wie jij bent als trader
                </h2>
              </div>
            </div>
            <p className="text-sm font-medium leading-relaxed text-slate-500">
              Finn gebruikt dit profiel om uitleg, waarschuwingen, setups en coaching op jouw stijl
              af te stemmen. Pas dit gerust aan als je horizon, risico of focus verandert.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {summaryChips.length > 0 ? (
              summaryChips.map((chip) => (
                <span
                  key={chip}
                  className="inline-flex rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-[10px] font-black uppercase tracking-[0.18em] text-blue-600"
                >
                  {chip}
                </span>
              ))
            ) : (
              <span className="inline-flex rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-[10px] font-black uppercase tracking-[0.18em] text-amber-700">
                Nog niet ingevuld
              </span>
            )}
            <button
              type="button"
              onClick={() => {
                setEditingProfile((current) => !current);
                setProfileError(null);
              }}
              className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-[11px] font-black uppercase tracking-[0.18em] text-slate-700 transition hover:border-blue-200 hover:bg-white"
            >
              <Pencil size={14} />
              {editingProfile ? "Sluiten" : "Profiel aanpassen"}
            </button>
          </div>
        </div>

        {loadingPreferences ? (
          <div className="flex items-center gap-3 rounded-3xl border border-slate-200 bg-white p-6 text-sm font-semibold text-slate-500">
            <Loader2 className="h-5 w-5 animate-spin text-blue-600" />
            Traderprofiel laden...
          </div>
        ) : editingProfile ? (
          <div className="space-y-6">
            <div className="grid grid-cols-1 gap-6">
              <MultiChoiceGroup
                title="Wat voor trader ben je?"
                subtitle="Kies een of meer stijlen die passen bij hoe jij normaal handelt of investeert."
                options={TRADER_TYPES}
                values={profileForm.trader_types}
                onToggle={(value) => toggleMulti("trader_types", value)}
              />

              <MultiChoiceGroup
                title="Welke timeframes gebruik je?"
                subtitle="Je kunt meerdere selecteren. Finn gebruikt dit om irrelevante signalen te dempen."
                options={TIMEFRAMES}
                values={profileForm.primary_timeframes}
                onToggle={(value) => toggleMulti("primary_timeframes", value)}
              />

              <MultiChoiceGroup
                title="Waar focus je op?"
                subtitle="Kies de markten of assets waar Finn in je context vooral rekening mee moet houden."
                options={ASSET_FOCUS}
                values={profileForm.asset_focus}
                onToggle={(value) => toggleMulti("asset_focus", value)}
              />

              <MultiChoiceGroup
                title="Wat is je doel?"
                subtitle="Kies een of meer doelen. Finn gebruikt dit om coaching en waarschuwingen op jouw intentie af te stemmen."
                options={GOALS}
                values={profileForm.investment_goals_list}
                onToggle={(value) => toggleMulti("investment_goals_list", value)}
              />

              <MultiChoiceGroup
                title="Hoeveel ervaring heb je?"
                subtitle="Kies wat nu het best bij je past. Je kunt meerdere lagen aanvinken als je tussen niveaus in zit."
                options={EXPERIENCE_LEVELS}
                values={profileForm.experience_levels}
                onToggle={(value) => toggleMulti("experience_levels", value)}
              />

              <MultiChoiceGroup
                title="Wat is je risicoprofiel?"
                subtitle="Zo kan Finn beter kiezen tussen remmen, waarschuwen of juist ruimte geven. Je kunt combineren als je per context verschilt."
                options={RISK_PROFILES}
                values={profileForm.risk_profiles}
                onToggle={(value) => toggleMulti("risk_profiles", value)}
              />
            </div>

            {profileError ? (
              <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">
                {profileError}
              </div>
            ) : null}

            <div className="flex flex-col gap-4 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm md:flex-row md:items-center md:justify-between">
              <p className="text-sm font-medium leading-relaxed text-slate-500">
                Werk dit profiel bij wanneer je stijl verandert. Dan blijft Finn relevant en krijg
                je minder signalen die niet bij jouw manier van traden passen.
              </p>
              <button
                type="button"
                onClick={handleSaveProfile}
                disabled={!hasCompleteProfile || savingProfile}
                className="inline-flex items-center justify-center gap-2 rounded-2xl bg-blue-600 px-5 py-3 text-[11px] font-black uppercase tracking-[0.18em] text-white shadow-lg shadow-blue-500/20 transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {savingProfile ? "Profiel opslaan..." : "Profiel opslaan"}
                <Save size={14} />
              </button>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">Stijl & doel</div>
              <div className="mt-4 space-y-4">
                <div>
                  <div className="text-sm font-black text-slate-900">Trader type</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {profileForm.trader_types.length > 0 ? (
                      profileForm.trader_types.map((value) => (
                        <span
                          key={value}
                          className="inline-flex rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-[11px] font-bold text-slate-700"
                        >
                          {traderTypeMap[value]}
                        </span>
                      ))
                    ) : (
                      <span className="text-sm font-semibold text-slate-500">Nog niet ingevuld</span>
                    )}
                  </div>
                </div>
                <div>
                  <div className="text-sm font-black text-slate-900">Doel</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {profileForm.investment_goals_list.length > 0 ? (
                      profileForm.investment_goals_list.map((value) => (
                        <span
                          key={value}
                          className="inline-flex rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-[11px] font-bold text-slate-700"
                        >
                          {goalsMap[value]}
                        </span>
                      ))
                    ) : (
                      <span className="text-sm font-semibold text-slate-500">Nog niet ingevuld</span>
                    )}
                  </div>
                </div>
                <div>
                  <div className="text-sm font-black text-slate-900">Risicoprofiel</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {profileForm.risk_profiles.length > 0 ? (
                      profileForm.risk_profiles.map((value) => (
                        <span
                          key={value}
                          className="inline-flex rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-[11px] font-bold text-slate-700"
                        >
                          {riskMap[value]}
                        </span>
                      ))
                    ) : (
                      <span className="text-sm font-semibold text-slate-500">Nog niet ingevuld</span>
                    )}
                  </div>
                </div>
              </div>
            </section>

            <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">Context voor Finn</div>
              <div className="mt-4 space-y-4">
                <div>
                  <div className="text-sm font-black text-slate-900">Timeframes</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {profileForm.primary_timeframes.length > 0 ? (
                      profileForm.primary_timeframes.map((value) => (
                        <span
                          key={value}
                          className="inline-flex rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-[11px] font-bold text-slate-700"
                        >
                          {timeframeMap[value]}
                        </span>
                      ))
                    ) : (
                      <span className="text-sm font-semibold text-slate-500">Nog niet ingevuld</span>
                    )}
                  </div>
                </div>
                <div>
                  <div className="text-sm font-black text-slate-900">Asset focus</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {profileForm.asset_focus.length > 0 ? (
                      profileForm.asset_focus.map((value) => (
                        <span
                          key={value}
                          className="inline-flex rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-[11px] font-bold text-slate-700"
                        >
                          {assetFocusMap[value]}
                        </span>
                      ))
                    ) : (
                      <span className="text-sm font-semibold text-slate-500">Nog niet ingevuld</span>
                    )}
                  </div>
                </div>
                <div>
                  <div className="text-sm font-black text-slate-900">Ervaring</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {profileForm.experience_levels.length > 0 ? (
                      profileForm.experience_levels.map((value) => (
                        <span
                          key={value}
                          className="inline-flex rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-[11px] font-bold text-slate-700"
                        >
                          {experienceMap[value]}
                        </span>
                      ))
                    ) : (
                      <span className="text-sm font-semibold text-slate-500">Nog niet ingevuld</span>
                    )}
                  </div>
                </div>
              </div>
            </section>
          </div>
        )}
      </div>

      {/* 3. ACTIONS */}
      <div className="bg-card border-2 border-[var(--color-border)] rounded-[2.5rem] p-10">
        <div className="text-[10px] font-black text-secondary uppercase tracking-widest mb-6">Strategic Terminal Actions</div>
        
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Link 
            href="/admin/ai" 
            className="flex items-center gap-4 p-5 rounded-2xl bg-[var(--color-border-subtle)] border-2 border-transparent hover:border-blue-600/30 transition-all group"
          >
            <div className="p-3 rounded-xl bg-card text-blue-600 border border-[var(--color-border)]">
              <Brain size={20} />
            </div>
            <div>
              <div className="text-sm font-black text-foreground tracking-tight group-hover:text-blue-600 transition-colors">AI Settings Interface</div>
              <div className="text-[10px] font-bold text-dim uppercase tracking-widest">Adjust intelligence parameters</div>
            </div>
          </Link>

          <button 
            onClick={handleLogout}
            disabled={loadingLogout}
            className="flex items-center gap-4 p-5 rounded-2xl bg-[var(--color-border-subtle)] border-2 border-transparent hover:border-rose-600/30 transition-all group text-left"
          >
            <div className="p-3 rounded-xl bg-card text-rose-600 border border-[var(--color-border)]">
              {loadingLogout ? <Loader2 size={20} className="animate-spin" /> : <LogOut size={20} />}
            </div>
            <div>
              <div className="text-sm font-black text-foreground tracking-tight group-hover:text-rose-600 transition-colors">Sign Out Securely</div>
              <div className="text-[10px] font-bold text-dim uppercase tracking-widest">Terminate current session</div>
            </div>
          </button>
        </div>
      </div>
      </div>
    </div>
  );
}
