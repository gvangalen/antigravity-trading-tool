"use client";

import { useState, useEffect } from "react";
import { useModal } from "@/components/modal/ModalProvider";
import { assistantChat } from "@/lib/api/ai";

import { generateExplanation } from "@/lib/api/setups";
import AILoader from "@/components/ui/AILoader";
import SetupForm from "@/components/setup/SetupForm";

import {
  Star,
  StarOff,
  Bot as BotIcon,
  Clock,
  Brain,
  Pencil,
  Trash,
  ChevronRight,
  Activity,
  Zap,
  Target,
  Rocket
} from "lucide-react";

import { useScoresData } from "@/hooks/useScoresData";
import { fetchStrategies } from "@/lib/api/strategy";
import { fetchBotConfigs } from "@/lib/api/botApi";
import { useTranslation } from "@/app/providers/I18nProvider";

const setupNameById = (setups, id) => {
  const setup = Array.isArray(setups) ? setups.find((item) => item.id === id) : null;
  return setup?.name || setup?.symbol;
};

/* =========================================================
   COMPONENT
========================================================= */
export default function SetupList({
  setups = [],
  loading,
  error,
  searchTerm = "",
  removeSetup,
  reload,
}) {
  const { t } = useTranslation();
  const copy = t?.setups?.list || {};
  const scoreLabel = (v) => {
    if (v <= 25) return copy.scoreVeryBearish;
    if (v <= 45) return copy.scoreBearish;
    if (v <= 60) return copy.scoreNeutral;
    if (v <= 75) return copy.scoreNeutralBullish;
    if (v <= 90) return copy.scoreBullish;
    return copy.scoreEuphoric;
  };
  const rangeText = (min, max) => `${scoreLabel(min)} → ${scoreLabel(max)}`;
  const { openConfirm, showSnackbar } = useModal();

  const [localSetups, setLocalSetups] = useState(setups);
  const [aiLoading, setAiLoading] = useState({});
  const [justUpdated, setJustUpdated] = useState({});
  const [finnPanels, setFinnPanels] = useState({});
  const [finnLoading, setFinnLoading] = useState({});
  
  const { macro, technical, market, loading: scoresLoading } = useScoresData();
  const [strategies, setStrategies] = useState([]);
  const [bots, setBots] = useState([]);

  useEffect(() => {
    setLocalSetups(setups);
  }, [setups]);

  useEffect(() => {
    async function loadExtraData() {
      try {
        const [sRes, bRes] = await Promise.all([
          fetchStrategies(),
          fetchBotConfigs()
        ]);
        setStrategies(sRes || []);
        setBots(bRes || []);
      } catch (err) {
        console.error("❌ Error loading lineage data:", err);
      }
    }
    loadExtraData();
  }, []);

  /* ---------------------------------------------------------
     FILTER
  --------------------------------------------------------- */
  const filteredSetups = !searchTerm
    ? localSetups
    : localSetups.filter((s) =>
        s.name?.toLowerCase().includes(searchTerm.toLowerCase())
      );

  /* ---------------------------------------------------------
     AI UITLEG
  --------------------------------------------------------- */
  async function handleGenerateExplanation(id) {
    try {
      setAiLoading((p) => ({ ...p, [id]: true }));

      const res = await generateExplanation(id);

      if (res?.explanation) {
        setLocalSetups((prev) =>
          prev.map((s) =>
            s.id === id ? { ...s, explanation: res.explanation } : s
          )
        );
      }

      showSnackbar(copy.aiSuccess, "success");

      setJustUpdated((p) => ({ ...p, [id]: true }));
      setTimeout(
        () => setJustUpdated((p) => ({ ...p, [id]: false })),
        1500
      );
    } catch (e) {
      console.error(e);
      showSnackbar(copy.aiFailed, "danger");
    } finally {
      setAiLoading((p) => ({ ...p, [id]: false }));
    }
  }

  async function handleFinnReview(setup) {
    try {
      setFinnLoading((p) => ({ ...p, [setup.id]: true }));
      const lineage = getLineage(setup.id);
      const context = {
        page: "/setup",
        page_type: "Setups",
        symbol: setup.symbol,
        setup_id: setup.id,
        strategy_id: lineage.strategy?.id || null,
      };
      const response = await assistantChat(
        `${copy.finnReviewPrompt.replace("{symbol}", setup.symbol)} ${copy.finnPlanPrompt.replace("{symbol}", setup.symbol)}`,
        context,
        []
      );
      const analysis = response?.analysis || response?.state?.analysis || null;
      setFinnPanels((p) => ({
        ...p,
        [setup.id]: {
          review: analysis,
          adherence: analysis,
        },
      }));
    } catch (e) {
      console.error(e);
      showSnackbar(copy.finnFailed, "danger");
    } finally {
      setFinnLoading((p) => ({ ...p, [setup.id]: false }));
    }
  }

  /* ---------------------------------------------------------
     DELETE
  --------------------------------------------------------- */
  function openDeleteModal(id) {
    openConfirm({
      title: copy.deleteTitle,
      statusLabel: copy.deleteStatus,
      tone: "danger",
      confirmText: copy.deleteConfirm,
      cancelText: copy.cancelAction,
      context: <p>{setupNameById(localSetups, id) || copy.setupFallbackName}</p>,
      impact: <p>{copy.deleteImpact}</p>,
      safety: <p>{copy.deleteSafety}</p>,
      consequence: <p>{copy.deleteConsequence}</p>,
      onConfirm: async () => {
        await removeSetup(id);
        reload && reload();
        showSnackbar(copy.deleteSuccess, "success");
      },
    });
  }

  /* ---------------------------------------------------------
     EDIT
  --------------------------------------------------------- */
  function openEditModal(setup) {
    openConfirm({
      title: `${copy.editTitle} – ${setup.name}`,
      statusLabel: copy.editStatus,
      tone: "primary",
      confirmText: copy.editConfirm,
      cancelText: copy.cancelAction,
      description: <SetupFormWrapper setup={setup} />,
      consequence: <p>{copy.editConsequence}</p>,
      onConfirm: () =>
        document.querySelector("#setup-edit-submit")?.click(),
    });
  }

  function SetupFormWrapper({ setup }) {
    return (
      <div className="space-y-6 pt-4">
        <SetupForm
          mode="edit"
          initialData={setup}
          onSaved={() => {
            reload && reload();
            showSnackbar(copy.editSuccess, "success");
          }}
        />
      </div>
    );
  }

  /* ---------------------------------------------------------
     LINEAGE & STATUS HELPERS
  --------------------------------------------------------- */
  const getSetupStatus = (setup) => {
    if (scoresLoading) return { active: false, label: copy.loadingStatus };
    
    const isMacroOk = macro.score >= setup.min_macro_score && macro.score <= setup.max_macro_score;
    const isTechOk = technical.score >= setup.min_technical_score && technical.score <= setup.max_technical_score;
    const isMarketOk = market.score >= setup.min_market_score && market.score <= setup.max_market_score;
    
    const active = isMacroOk && isTechOk && isMarketOk;
    return { 
      active, 
      label: active ? copy.activeLabel : copy.standbyLabel,
      reasons: { macro: isMacroOk, tech: isTechOk, market: isMarketOk }
    };
  };

  const getLineage = (setupId) => {
    const strategy = strategies.find(s => s.setup_id === setupId);
    const bot = strategy ? bots.find(b => b.strategy_id === strategy.id) : null;
    return { strategy, bot };
  };

  /* ---------------------------------------------------------
     RENDER
  --------------------------------------------------------- */
  return (
    <div className="space-y-6 mt-4">
      {loading && (
        <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40 px-4 py-3 text-sm text-slate-600 dark:text-slate-300">
          {copy.loadingBanner}
        </div>
      )}
      {error && (
        <div className="rounded-2xl border border-red-200 dark:border-red-900/40 bg-red-50 dark:bg-red-950/20 px-4 py-3 text-sm text-red-700 dark:text-red-300">
          {copy.errorBanner}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
        {filteredSetups.length > 0 ? (
          filteredSetups.map((setup) => (
            <div
              key={setup.id}
              className={`
                relative rounded-3xl p-6 sm:p-8
                border-2 border-slate-100
                bg-gradient-to-br from-white to-slate-50/50
                transition-all duration-300
                hover:border-blue-600/30
                ${justUpdated[setup.id] ? "ring-4 ring-green-600/10" : ""}
              `}
            >
              {(() => {
                const finnPanel = finnPanels[setup.id] || {};
                const finnBusy = !!finnLoading[setup.id];
                const lineage = getLineage(setup.id);
                return (
                  <>
              {/* AI overlay */}
              {aiLoading[setup.id] && (
                <div className="absolute inset-0 z-20 rounded-2xl bg-white/60 backdrop-blur-sm flex items-center justify-center">
                  <AILoader variant="dots" size="md" text={copy.analyzing} />
                </div>
              )}

              {/* Favorite */}
              <button
                onClick={() =>
                  openEditModal({ ...setup, favorite: !setup.favorite })
                }
                className="absolute top-4 right-4 text-secondary hover:text-yellow-500 z-10"
              >
                {setup.favorite ? (
                  <Star size={18} className="text-yellow-500 fill-yellow-500" />
                ) : (
                  <StarOff size={18} />
                )}
              </button>

              {/* HEADER: SYMBOL & STATUS */}
              <div className="flex items-center justify-between mb-4">
                 <div className="flex items-center gap-2">
                    <div className="bg-[var(--primary-soft)] text-[var(--primary-dark)] px-3 py-1 rounded-lg text-sm font-black tracking-tighter">
                       {setup.symbol}
                    </div>
                    <div className="bg-[var(--color-border-subtle)] text-muted px-2 py-1 rounded-lg text-[10px] font-bold">
                       {setup.timeframe}
                    </div>
                 </div>
                 
                 {(() => {
                    const status = getSetupStatus(setup);
                    const gaps = [];
                    if (!scoresLoading) {
                      if (macro.score < setup.min_macro_score) gaps.push(`Macro (> ${setup.min_macro_score})`);
                      if (macro.score > setup.max_macro_score) gaps.push(`Macro (< ${setup.max_macro_score})`);
                      if (technical.score < setup.min_technical_score) gaps.push(`Tech (> ${setup.min_technical_score})`);
                      if (technical.score > setup.max_technical_score) gaps.push(`Tech (< ${setup.max_technical_score})`);
                      if (market.score < setup.min_market_score) gaps.push(`Markt (> ${setup.min_market_score})`);
                      if (market.score > setup.max_market_score) gaps.push(`Markt (< ${setup.max_market_score})`);
                    }

                    return (
                      <div className="flex flex-col items-end gap-1.5">
                        <div className={`flex items-center gap-1.5 px-2 py-1 rounded-full text-[9px] font-black tracking-widest border ${
                          status.active 
                            ? 'bg-green-50 text-green-600 border-green-200' 
                            : 'bg-slate-50 text-secondary border-slate-200'
                        }`}>
                           <Activity size={10} className={status.active ? "animate-pulse" : ""} />
                           {status.label}
                        </div>
                        
                        {/* Gap Analysis */}
                        <div className="text-[9px] font-bold text-right">
                           {status.active ? (
                              <span className="text-green-500/70 uppercase tracking-tighter">
                                {copy.allConditionsMet}
                              </span>
                           ) : (
                              <div className="flex flex-col gap-0.5 items-end opacity-60">
                                 {gaps.map((gap, i) => (
                                    <span key={i} className="text-secondary">
                                      {copy.waitingForPrefix} {gap}
                                    </span>
                                 ))}
                              </div>
                           )}
                        </div>
                      </div>
                    );
                 })()}
              </div>

              {/* TITLE & TYPE */}
              <div className="mb-4">
                <h3 className="font-black text-[var(--text-dark)] leading-tight uppercase text-base tracking-tight">{setup.name}</h3>
                <p className="text-[10px] text-[var(--text-light)] font-bold uppercase tracking-widest mt-1 flex items-center gap-1">
                  {setup.setup_type === 'dca' ? <Rocket size={10} /> : <Target size={10} />}
                  {setup.setup_type || copy.customBlueprint} {copy.blueprintSuffix}
                </p>
              </div>

              {/* SCORE RANGES */}
              <div className="space-y-3 bg-card p-5 rounded-2xl border-2 border-slate-50">
                <div>
                  <strong>{copy.macroLabel}:</strong>{" "}
                  {setup.min_macro_score}–{setup.max_macro_score}
                  <div className="opacity-70">
                    {rangeText(
                      setup.min_macro_score,
                      setup.max_macro_score
                    )}
                  </div>
                </div>

                <div>
                  <strong>{copy.technicalLabel}:</strong>{" "}
                  {setup.min_technical_score}–{setup.max_technical_score}
                  <div className="opacity-70">
                    {rangeText(
                      setup.min_technical_score,
                      setup.max_technical_score
                    )}
                  </div>
                </div>

                <div>
                  <strong>{copy.marketLabel}:</strong>{" "}
                  {setup.min_market_score}–{setup.max_market_score}
                  <div className="opacity-70">
                    {rangeText(
                      setup.min_market_score,
                      setup.max_market_score
                    )}
                  </div>
                </div>
              </div>

              {/* UITLEG */}
              <div className="mt-4 text-xs font-medium text-dim leading-relaxed bg-slate-50/50 p-5 rounded-2xl border-2 border-slate-50">
                {setup.explanation || copy.noExplanation}
              </div>

              {(finnPanel.review || finnPanel.adherence) && (
                <div className="mt-4 space-y-3 rounded-2xl border border-slate-200 bg-slate-50/70 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2 text-slate-600">
                      <Brain size={15} className="text-violet-500" />
                  <span className="text-[10px] font-black uppercase tracking-widest">{copy.finnCheck}</span>
                    </div>
                    {finnBusy && <span className="text-[9px] font-black uppercase tracking-widest text-slate-400">{copy.loadingShort}</span>}
                  </div>

                  {finnPanel.review && (
                    <div className={`rounded-xl border p-3 ${
                      finnPanel.review.decision_status === "block"
                        ? "border-rose-200 bg-rose-50 text-rose-700"
                        : finnPanel.review.decision_status === "modify" || finnPanel.review.decision_status === "insufficient_context"
                          ? "border-amber-200 bg-amber-50 text-amber-700"
                          : "border-emerald-200 bg-emerald-50 text-emerald-700"
                    }`}>
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-[9px] font-black uppercase tracking-widest">{copy.setupReview}</span>
                        <span className="text-[8px] font-black uppercase tracking-widest">{finnPanel.review.decision_status}</span>
                      </div>
                      <p className="mt-2 text-xs font-semibold leading-relaxed">{finnPanel.review.risk_summary}</p>
                      {finnPanel.review.portfolio_impact?.message && (
                        <p className="mt-2 text-[11px] font-semibold leading-relaxed opacity-80">{finnPanel.review.portfolio_impact.message}</p>
                      )}
                    </div>
                  )}

                  {finnPanel.adherence && (
                    <div className={`rounded-xl border p-3 ${
                      finnPanel.adherence.adherence_status === "in_plan"
                        ? "border-blue-200 bg-blue-50 text-blue-700"
                        : finnPanel.adherence.adherence_status === "insufficiently_justified"
                          ? "border-amber-200 bg-amber-50 text-amber-700"
                          : "border-rose-200 bg-rose-50 text-rose-700"
                    }`}>
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-[9px] font-black uppercase tracking-widest">{copy.planAdherence}</span>
                        <span className="text-[8px] font-black uppercase tracking-widest">{finnPanel.adherence.adherence_status}</span>
                      </div>
                      <p className="mt-2 text-xs font-semibold leading-relaxed">{finnPanel.adherence.adherence_reason}</p>
                      {finnPanel.adherence.suggested_recovery_step && (
                        <p className="mt-2 text-[11px] font-semibold leading-relaxed opacity-80">{finnPanel.adherence.suggested_recovery_step}</p>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* AI knop */}
              <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
                <button
                  onClick={() => handleGenerateExplanation(setup.id)}
                  disabled={aiLoading[setup.id]}
                  className="w-full flex items-center justify-center gap-3 px-4 py-3 rounded-xl text-[10px] font-black uppercase tracking-widest text-blue-600 bg-blue-50 hover:bg-blue-100 transition-all border-2 border-blue-100/50"
                >
                  <BotIcon size={16} />
                  {aiLoading[setup.id]
                    ? copy.analyzing
                    : setup.explanation
                    ? copy.reanalyzeBlueprint
                    : copy.analyzeBlueprint}
                </button>
                <button
                  onClick={() => handleFinnReview(setup)}
                  disabled={finnBusy}
                  className="w-full flex items-center justify-center gap-3 px-4 py-3 rounded-xl text-[10px] font-black uppercase tracking-widest text-violet-600 bg-violet-50 hover:bg-violet-100 transition-all border-2 border-violet-100/50"
                >
                  <Brain size={16} />
                  {finnBusy ? copy.finnChecking : copy.checkWithFinn}
                </button>
              </div>

              {/* ⛓️ LINEAGE VIEW */}
              <div className="mt-6 pt-4 border-t border-slate-100 italic">
                 <div className="flex items-center justify-between gap-1 text-[9px] uppercase font-black text-secondary tracking-tighter">
                    <div className="flex flex-col items-center gap-1 flex-1">
                       <span className="text-[var(--primary)]">Setup</span>
                       <span className="text-dim truncate max-w-[60px]">{setup.symbol}</span>
                    </div>
                    <ChevronRight size={12} className="opacity-30 mt-3" />
                    <div className="flex flex-col items-center gap-1 flex-1">
                       <span>{copy.strategyLabel}</span>
                       <span className={lineage.strategy ? "text-green-600 truncate max-w-[60px]" : "opacity-40"}>
                          {lineage.strategy?.name || copy.none}
                       </span>
                    </div>
                    <ChevronRight size={12} className="opacity-30 mt-3" />
                    <div className="flex flex-col items-center gap-1 flex-1">
                       <span>{copy.botLabel}</span>
                       <span className={lineage.bot?.is_active ? "text-purple-600" : "opacity-40 text-red-400"}>
                          {lineage.bot ? (lineage.bot.is_active ? copy.botActive : copy.botPaused) : copy.none}
                       </span>
                    </div>
                 </div>
              </div>

              {/* Acties */}
              <div className="flex justify-between items-center mt-8 pt-6 border-t-2 border-slate-100">
                <button
                  onClick={() => openDeleteModal(setup.id)}
                  className="text-[10px] font-black uppercase text-red-500 hover:text-red-600 tracking-[0.2em] transition-all flex items-center gap-2 px-2"
                >
                  <Trash size={12} /> {copy.deleteAction}
                </button>
                
                <button
                  onClick={() => openEditModal(setup)}
                  className="flex items-center gap-3 px-6 py-3 rounded-xl text-[11px] font-black uppercase tracking-widest bg-slate-900 text-white hover:bg-black transition-all shadow-sm active:scale-95"
                >
                  <Pencil size={12} /> {copy.editAction}
                </button>
              </div>
                  </>
                );
              })()}
            </div>
          ))
        ) : (
          <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40 px-4 py-4 text-sm text-slate-600 dark:text-slate-300">
            {copy.emptyState}
          </div>
        )}
      </div>
    </div>
  );
}
