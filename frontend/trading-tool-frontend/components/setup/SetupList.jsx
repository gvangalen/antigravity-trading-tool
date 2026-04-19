"use client";

import { useState, useEffect } from "react";
import { useModal } from "@/components/modal/ModalProvider";

import { generateExplanation } from "@/lib/api/setups";
import AILoader from "@/components/ui/AILoader";

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
  Target
} from "lucide-react";

import { useScoresData } from "@/hooks/useScoresData";
import { fetchStrategies } from "@/lib/api/strategy";
import { fetchBotConfigs } from "@/lib/api/botApi";

/* =========================================================
   🧠 SCORE INTERPRETATIE
========================================================= */
const scoreLabel = (v) => {
  if (v <= 25) return "Sterk bearish / risk-off";
  if (v <= 45) return "Bearish";
  if (v <= 60) return "Neutraal";
  if (v <= 75) return "Neutraal → bullish";
  if (v <= 90) return "Bullish";
  return "Euforisch / oververhit";
};

const rangeText = (min, max) =>
  `${scoreLabel(min)} → ${scoreLabel(max)}`;

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
  const { openConfirm, showSnackbar } = useModal();

  const [localSetups, setLocalSetups] = useState(setups);
  const [aiLoading, setAiLoading] = useState({});
  const [justUpdated, setJustUpdated] = useState({});
  
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

      showSnackbar("AI-uitleg succesvol gegenereerd", "success");

      setJustUpdated((p) => ({ ...p, [id]: true }));
      setTimeout(
        () => setJustUpdated((p) => ({ ...p, [id]: false })),
        1500
      );
    } catch (e) {
      console.error(e);
      showSnackbar("AI generatie mislukt", "danger");
    } finally {
      setAiLoading((p) => ({ ...p, [id]: false }));
    }
  }

  /* ---------------------------------------------------------
     DELETE
  --------------------------------------------------------- */
  function openDeleteModal(id) {
    openConfirm({
      title: "Setup verwijderen",
      tone: "danger",
      confirmText: "Verwijderen",
      cancelText: "Annuleren",
      description: (
        <p>
          Weet je zeker dat je deze setup wilt verwijderen?
          <br />
          <span className="text-red-600 font-medium">
            Dit kan niet ongedaan worden gemaakt.
          </span>
        </p>
      ),
      onConfirm: async () => {
        await removeSetup(id);
        reload && reload();
        showSnackbar("Setup verwijderd", "success");
      },
    });
  }

  /* ---------------------------------------------------------
     EDIT
  --------------------------------------------------------- */
  function openEditModal(setup) {
    openConfirm({
      title: `Setup bewerken – ${setup.name}`,
      tone: "primary",
      confirmText: "Opslaan",
      cancelText: "Annuleren",
      description: <SetupFormWrapper setup={setup} />,
      onConfirm: () =>
        document.querySelector("#setup-edit-submit")?.click(),
    });
  }

  function SetupFormWrapper({ setup }) {
    const SetupForm =
      require("@/components/setup/SetupForm").default;

    return (
      <div className="space-y-6 pt-4">
        <SetupForm
          mode="edit"
          initialData={setup}
          onSaved={() => {
            reload && reload();
            showSnackbar("Setup bijgewerkt", "success");
          }}
        />
      </div>
    );
  }

  /* ---------------------------------------------------------
     LINEAGE & STATUS HELPERS
  --------------------------------------------------------- */
  const getSetupStatus = (setup) => {
    if (scoresLoading) return { active: false, label: "Loading..." };
    
    const isMacroOk = macro.score >= setup.min_macro_score && macro.score <= setup.max_macro_score;
    const isTechOk = technical.score >= setup.min_technical_score && technical.score <= setup.max_technical_score;
    const isMarketOk = market.score >= setup.min_market_score && market.score <= setup.max_market_score;
    
    const active = isMacroOk && isTechOk && isMarketOk;
    return { 
      active, 
      label: active ? "ACTIVE" : "STANDBY",
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
      {loading && <p className="text-sm text-gray-500">Setups laden…</p>}
      {error && <p className="text-sm text-red-500">{error}</p>}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
        {filteredSetups.length > 0 ? (
          filteredSetups.map((setup) => (
            <div
              key={setup.id}
              className={`
                relative rounded-3xl p-8
                border-2 border-slate-100
                bg-gradient-to-br from-white to-slate-50/50
                transition-all duration-300
                hover:border-blue-600/30
                ${justUpdated[setup.id] ? "ring-4 ring-green-600/10" : ""}
              `}
            >
              {/* AI overlay */}
              {aiLoading[setup.id] && (
                <div className="absolute inset-0 z-20 rounded-2xl bg-white/60 backdrop-blur-sm flex items-center justify-center">
                  <AILoader variant="dots" size="md" text="AI analyse…" />
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
                      if (market.score < setup.min_market_score) gaps.push(`Market (> ${setup.min_market_score})`);
                      if (market.score > setup.max_market_score) gaps.push(`Market (< ${setup.max_market_score})`);
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
                              <span className="text-green-500/70 uppercase tracking-tighter">✓ Alle voorwaarden voldaan</span>
                           ) : (
                              <div className="flex flex-col gap-0.5 items-end opacity-60">
                                 {gaps.map((gap, i) => (
                                    <span key={i} className="text-secondary">Waiting for {gap}</span>
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
                  {setup.setup_type || 'Custom'} Blueprint
                </p>
              </div>

              {/* SCORE RANGES */}
              <div className="space-y-3 bg-card p-5 rounded-2xl border-2 border-slate-50">
                <div>
                  <strong>Macro:</strong>{" "}
                  {setup.min_macro_score}–{setup.max_macro_score}
                  <div className="opacity-70">
                    {rangeText(
                      setup.min_macro_score,
                      setup.max_macro_score
                    )}
                  </div>
                </div>

                <div>
                  <strong>Technical:</strong>{" "}
                  {setup.min_technical_score}–{setup.max_technical_score}
                  <div className="opacity-70">
                    {rangeText(
                      setup.min_technical_score,
                      setup.max_technical_score
                    )}
                  </div>
                </div>

                <div>
                  <strong>Market:</strong>{" "}
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
                {setup.explanation || "Geen uitleg beschikbaar."}
              </div>

              {/* AI knop */}
              <button
                onClick={() => handleGenerateExplanation(setup.id)}
                disabled={aiLoading[setup.id]}
                className="mt-4 w-full flex items-center justify-center gap-3 px-4 py-3 rounded-xl text-[10px] font-black uppercase tracking-widest text-blue-600 bg-blue-50 hover:bg-blue-100 transition-all border-2 border-blue-100/50"
              >
                <BotIcon size={16} />
                {aiLoading[setup.id]
                  ? "ANALYZING…"
                  : setup.explanation
                  ? "Re-Analyze Blueprint"
                  : "Analyze Strategy DNA"}
              </button>

              {/* ⛓️ LINEAGE VIEW */}
              <div className="mt-6 pt-4 border-t border-slate-100 italic">
                 <div className="flex items-center justify-between gap-1 text-[9px] uppercase font-black text-secondary tracking-tighter">
                    <div className="flex flex-col items-center gap-1 flex-1">
                       <span className="text-[var(--primary)]">Setup</span>
                       <span className="text-dim truncate max-w-[60px]">{setup.symbol}</span>
                    </div>
                    <ChevronRight size={12} className="opacity-30 mt-3" />
                    <div className="flex flex-col items-center gap-1 flex-1">
                       <span>Strategy</span>
                       <span className={getLineage(setup.id).strategy ? "text-green-600 truncate max-w-[60px]" : "opacity-40"}>
                          {getLineage(setup.id).strategy?.name || "None"}
                       </span>
                    </div>
                    <ChevronRight size={12} className="opacity-30 mt-3" />
                    <div className="flex flex-col items-center gap-1 flex-1">
                       <span>Bot</span>
                       <span className={getLineage(setup.id).bot?.is_active ? "text-purple-600" : "opacity-40 text-red-400"}>
                          {getLineage(setup.id).bot ? (getLineage(setup.id).bot.is_active ? "Running" : "Paused") : "None"}
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
                  <Trash size={12} /> Verwijderen
                </button>
                
                <button
                  onClick={() => openEditModal(setup)}
                  className="flex items-center gap-3 px-6 py-3 rounded-xl text-[11px] font-black uppercase tracking-widest bg-slate-900 text-white hover:bg-black transition-all shadow-sm active:scale-95"
                >
                  <Pencil size={12} /> Bewerken
                </button>
              </div>
            </div>
          ))
        ) : (
          <p className="text-sm text-gray-500">Geen setups gevonden.</p>
        )}
      </div>
    </div>
  );
}
