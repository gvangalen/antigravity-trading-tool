"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAsset } from "@/app/providers/AssetProvider";
import { Search, X, Command, ArrowRight, Sparkles, Workflow, Bitcoin } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useWatchlist } from "@/hooks/useWatchlist";
import { useActiveSetup } from "@/app/providers/SetupProvider";
import { useTranslation } from "@/app/providers/I18nProvider";
import { useModal } from "@/components/modal/ModalProvider";
import IndicatorConfigModal from "@/components/scoring/IndicatorConfigModal";
import { getIndicatorNames as getTechnicalIndicatorNames, technicalDataAdd } from "@/lib/api/technical";
import { getMacroIndicatorNames, macroDataAdd } from "@/lib/api/macro";
import { getMarketIndicatorNames, marketIndicatorAdd } from "@/lib/api/market";

const SEARCH_OPEN_EVENT = "finn-command-search:open";

const ASSETS = [
  { symbol: "BTC", name: "Bitcoin", icon: "₿" },
  { symbol: "ETH", name: "Ethereum", icon: "Ξ" },
  { symbol: "SOL", name: "Solana", icon: "S" },
  { symbol: "ADA", name: "Cardano", icon: "A" },
  { symbol: "DOT", name: "Polkadot", icon: "P" },
];

const WORKFLOWS = [
  { id: "overview", label: "Overview", href: (symbol) => `/asset?symbol=${symbol}&tab=overview`, category: "Workflow" },
  { id: "market", label: "Market Context", href: (symbol) => `/market?symbol=${symbol}&step=market`, category: "Workflow" },
  { id: "macro", label: "Macro Context", href: (symbol) => `/macro?symbol=${symbol}&step=macro`, category: "Workflow" },
  { id: "technical", label: "Technical Context", href: (symbol) => `/technical?symbol=${symbol}&step=technical`, category: "Workflow" },
  { id: "conclusion", label: "FINN Conclusion", href: (symbol) => `/technical?symbol=${symbol}&step=conclusion`, category: "Workflow" },
  { id: "setup", label: "Setups", href: (symbol) => `/setup?symbol=${symbol}`, category: "Workflow" },
  { id: "strategy", label: "Strategies", href: (symbol) => `/strategy?symbol=${symbol}`, category: "Workflow" },
  { id: "bot", label: "Bots", href: (symbol) => `/bot?symbol=${symbol}`, category: "Workflow" },
  { id: "report", label: "Reports", href: (symbol) => `/report?symbol=${symbol}`, category: "Workflow" },
];

const ACTIONS = [
  {
    id: "add-technical-indicator",
    label: "Indicator toevoegen",
    description: "Open Technical indicator mode",
    category: "Action",
    mode: "indicator",
  },
];

function normalize(text) {
  return String(text || "").trim().toLowerCase();
}

export default function AssetSearchBar() {
  const { t } = useTranslation();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { selectedAsset, setSelectedAsset } = useAsset();
  const { setActiveSetup, setFocusedBotId } = useActiveSetup();
  const { isInWatchlist, add, remove } = useWatchlist();
  const { showSnackbar } = useModal();
  const [query, setQuery] = useState("");
  const [isOpen, setIsOpen] = useState(false);
  const [mode, setMode] = useState({ kind: "all", category: null });
  const [technicalIndicators, setTechnicalIndicators] = useState([]);
  const [macroIndicators, setMacroIndicators] = useState([]);
  const [marketIndicators, setMarketIndicators] = useState([]);
  const [pendingIndicator, setPendingIndicator] = useState(null);
  const containerRef = useRef(null);
  const inputRef = useRef(null);

  const activeSymbol = searchParams.get("symbol")?.toUpperCase() || selectedAsset || "BTC";

  useEffect(() => {
    let mounted = true;

    async function loadIndicators() {
      try {
        const [technicalList, macroList, marketList] = await Promise.all([
          getTechnicalIndicatorNames(),
          getMacroIndicatorNames(),
          getMarketIndicatorNames(),
        ]);

        if (mounted) {
          setTechnicalIndicators(Array.isArray(technicalList) ? technicalList : []);
          setMacroIndicators(Array.isArray(macroList) ? macroList : []);
          setMarketIndicators(Array.isArray(marketList) ? marketList : []);
        }
      } catch (error) {
        console.error("Failed to load indicators for command search:", error);
      }
    }

    loadIndicators();
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    function handleClickOutside(event) {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    }

    function handleOpenSearch(event) {
      const nextMode = event?.detail?.mode === "indicator"
        ? { kind: "indicator", category: event?.detail?.category || "technical" }
        : { kind: "all", category: null };

      setMode(nextMode);
      setQuery(event?.detail?.query || "");
      setIsOpen(true);

      requestAnimationFrame(() => {
        inputRef.current?.focus();
      });
    }

    document.addEventListener("mousedown", handleClickOutside);
    window.addEventListener(SEARCH_OPEN_EVENT, handleOpenSearch);

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      window.removeEventListener(SEARCH_OPEN_EVENT, handleOpenSearch);
    };
  }, []);

  const indicatorResults = useMemo(() => {
    const sources = [
      {
        key: "technical",
        label: "Technical indicator",
        actionLabel: "Toevoegen aan Technical",
        route: (symbol, name) => `/technical?symbol=${encodeURIComponent(symbol)}&step=technical&technicalIndicator=${encodeURIComponent(name)}`,
        items: technicalIndicators,
      },
      {
        key: "macro",
        label: "Macro indicator",
        actionLabel: "Toevoegen aan Macro",
        route: (symbol, name) => `/macro?symbol=${encodeURIComponent(symbol)}&step=macro&macroIndicator=${encodeURIComponent(name)}`,
        items: macroIndicators,
      },
      {
        key: "market",
        label: "Market indicator",
        actionLabel: "Toevoegen aan Market",
        route: (symbol, name) => `/market?symbol=${encodeURIComponent(symbol)}&step=market&marketIndicator=${encodeURIComponent(name)}`,
        items: marketIndicators,
      },
    ];

    const activeSources =
      mode.kind === "indicator" && mode.category
        ? sources.filter((source) => source.key === mode.category)
        : sources;

    return activeSources
      .flatMap((source) =>
        source.items
          .filter((indicator) => {
            if (mode.kind !== "indicator" && query.trim() === "") return false;
            if (mode.kind === "indicator" && query.trim() === "") return true;

            const haystack = [
              indicator?.display_name,
              indicator?.name,
              source.label,
              "indicator",
            ]
              .filter(Boolean)
              .join(" ")
              .toLowerCase();

            return haystack.includes(normalize(query));
          })
          .map((indicator) => ({
            id: `${source.key}:${indicator.name}`,
            type: "indicator",
            title: indicator.display_name || indicator.label || indicator.name,
            subtitle: source.label,
            actionLabel: source.actionLabel,
            indicatorName: indicator.name,
            indicatorCategory: source.key,
            href: source.route(activeSymbol, indicator.name),
          }))
      )
      .slice(0, 12);
  }, [activeSymbol, macroIndicators, marketIndicators, mode.category, mode.kind, query, technicalIndicators]);

  const assetResults = useMemo(() => {
    if (mode.kind === "indicator") return [];
    if (query.trim() === "") return [];

    return ASSETS.filter((asset) => {
      const haystack = `${asset.symbol} ${asset.name}`.toLowerCase();
      return haystack.includes(normalize(query));
    }).map((asset) => ({
      id: `asset:${asset.symbol}`,
      type: "asset",
      title: asset.symbol,
      subtitle: asset.name,
      icon: asset.icon,
      asset,
    }));
  }, [mode.kind, query]);

  const workflowResults = useMemo(() => {
    if (mode.kind === "indicator") return [];
    if (query.trim() === "") return [];

    return WORKFLOWS.filter((workflow) => {
      const haystack = `${workflow.label} ${workflow.id} workflow`.toLowerCase();
      return haystack.includes(normalize(query));
    }).map((workflow) => ({
      id: `workflow:${workflow.id}`,
      type: "workflow",
      title: workflow.label,
      subtitle: workflow.category,
      href: workflow.href(activeSymbol),
    }));
  }, [activeSymbol, mode.kind, query]);

  const actionResults = useMemo(() => {
    if (query.trim() === "" && mode.kind !== "indicator") return [];

    return ACTIONS.filter((action) => {
      if (mode.kind === "indicator") return action.mode === "indicator";
      const haystack = `${action.label} ${action.description} ${action.category}`.toLowerCase();
      return haystack.includes(normalize(query));
    }).map((action) => ({
      id: `action:${action.id}`,
      type: "action",
      title: action.label,
      subtitle: action.description,
      action,
    }));
  }, [mode.kind, query]);

  const results = useMemo(
    () => [...actionResults, ...assetResults, ...workflowResults, ...indicatorResults],
    [actionResults, assetResults, indicatorResults, workflowResults]
  );

  const resetSearch = () => {
    setQuery("");
    setIsOpen(false);
    setMode({ kind: "all", category: null });
  };

  const handleSelectAsset = (symbol) => {
    setActiveSetup(null);
    setFocusedBotId(null);
    setSelectedAsset(symbol);

    import("@/lib/api/market").then(({ initializeAsset }) => {
      initializeAsset(symbol).catch((err) => console.error("❌ Init error:", err));
    });

    router.push(`/asset?symbol=${symbol}&tab=overview`);
    resetSearch();
  };

  const handleToggleWatchlist = (event, symbol) => {
    event.stopPropagation();
    if (isInWatchlist(symbol)) {
      remove(symbol);
      return;
    }

    add(symbol);
    import("@/lib/api/market").then(({ initializeAsset }) => {
      initializeAsset(symbol).catch((err) => console.error("❌ Init error:", err));
    });
  };

  const handleSelectResult = async (result) => {
    if (result.type === "asset") {
      handleSelectAsset(result.asset.symbol);
      return;
    }

    if (result.type === "workflow") {
      router.push(result.href);
      resetSearch();
      return;
    }

    if (result.type === "action") {
      setMode({ kind: result.action.mode || "all", category: "technical" });
      setQuery("");
      setIsOpen(true);
      requestAnimationFrame(() => {
        inputRef.current?.focus();
      });
      return;
    }

    if (result.type === "indicator") {
      try {
        resetSearch();
        setPendingIndicator({
          category: result.indicatorCategory,
          indicatorName: result.indicatorName,
          title: result.title,
        });
      } catch (error) {
        console.error("Failed to open indicator config from command search:", error);
        showSnackbar(`Openen van ${result.title} is mislukt.`, "danger");
      }
    }
  };

  const showEmptyState = isOpen && results.length === 0 && (query.trim() !== "" || mode.kind === "indicator");

  return (
    <div className="relative w-full max-w-xl mx-4" ref={containerRef}>
      <div className="relative group">
        <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none text-slate-400 group-focus-within:text-blue-500 transition-colors">
          <Search size={16} strokeWidth={2.5} />
        </div>

        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setIsOpen(true);
            if (mode.kind !== "indicator") {
              setMode({ kind: "all", category: null });
            }
          }}
          onFocus={() => setIsOpen(true)}
          placeholder={mode.kind === "indicator" ? "Zoek indicator voor Technical..." : t?.common?.searchAssetPlaceholder}
          className="w-full bg-slate-100/50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800 rounded-2xl py-2.5 pl-11 pr-12 text-sm font-bold text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500/50 transition-all"
        />

        <div className="absolute inset-y-0 right-0 pr-4 flex items-center gap-2 pointer-events-none">
          <div className="hidden sm:flex items-center gap-1 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 px-1.5 py-0.5 rounded-md text-[10px] font-black text-slate-400 uppercase tracking-tighter">
            <Command size={10} />
            K
          </div>
          {(query || mode.kind === "indicator") && (
            <button
              type="button"
              onClick={resetSearch}
              className="pointer-events-auto text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
            >
              <X size={14} />
            </button>
          )}
        </div>
      </div>

      <AnimatePresence>
        {isOpen && results.length > 0 ? (
          <motion.div
            initial={{ opacity: 0, y: 10, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.98 }}
            className="absolute top-full left-0 right-0 mt-2 bg-white dark:bg-[#0f172a] border border-slate-200 dark:border-slate-800 rounded-2xl shadow-2xl z-[100] overflow-hidden"
          >
            <div className="p-2">
              <div className="px-3 py-2 text-[10px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest border-b border-slate-50 dark:border-slate-800/50 mb-1">
                {mode.kind === "indicator" ? "Technical Indicators" : "Command Search"}
              </div>

              <div className="max-h-[420px] overflow-y-auto space-y-1">
                {results.map((result) => (
                  <div
                    key={result.id}
                    onClick={() => handleSelectResult(result)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        handleSelectResult(result);
                      }
                    }}
                    role="button"
                    tabIndex={0}
                    className="w-full rounded-xl px-3 py-3 text-left transition-all hover:bg-slate-50 dark:hover:bg-slate-800/50"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex min-w-0 items-center gap-3">
                        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-300">
                          {result.type === "asset" ? (
                            <span className="text-sm font-black">{result.icon}</span>
                          ) : result.type === "indicator" ? (
                            <Sparkles size={16} />
                          ) : result.type === "workflow" ? (
                            <Workflow size={16} />
                          ) : (
                            <Bitcoin size={16} />
                          )}
                        </div>
                        <div className="min-w-0">
                          <div className="truncate text-xs font-black uppercase tracking-tight text-slate-900 dark:text-slate-100">
                            {result.title}
                          </div>
                          <div className="truncate text-[11px] font-semibold text-slate-400">
                            {result.subtitle}
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        {result.type === "asset" ? (
                          <button
                            type="button"
                            onClick={(event) => handleToggleWatchlist(event, result.asset.symbol)}
                            className={`rounded-lg p-1.5 transition-all ${
                              isInWatchlist(result.asset.symbol)
                                ? "text-amber-400 hover:bg-amber-400/10"
                                : "text-slate-300 hover:bg-slate-100 dark:text-slate-600 dark:hover:bg-slate-700"
                            }`}
                          >
                            <svg
                              viewBox="0 0 24 24"
                              fill={isInWatchlist(result.asset.symbol) ? "currentColor" : "none"}
                              stroke="currentColor"
                              strokeWidth="2.5"
                              className="w-4 h-4"
                            >
                              <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
                            </svg>
                          </button>
                        ) : null}

                        {result.actionLabel ? (
                          <span className="hidden rounded-full border border-blue-100 bg-blue-50 px-2.5 py-1 text-[10px] font-black uppercase tracking-[0.2em] text-blue-600 md:inline-flex">
                            {result.actionLabel}
                          </span>
                        ) : null}

                        <ArrowRight size={14} className="text-slate-300" />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </motion.div>
        ) : null}

        {showEmptyState ? (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="absolute top-full left-0 right-0 mt-2 bg-white dark:bg-[#0f172a] border border-slate-200 dark:border-slate-800 rounded-2xl shadow-2xl z-[100] p-8 text-center"
          >
            <div className="flex flex-col items-center gap-3">
              <div className="w-12 h-12 rounded-full bg-slate-50 dark:bg-slate-800/50 flex items-center justify-center text-slate-300">
                <Search size={24} />
              </div>
              <div>
                <div className="text-sm font-black text-slate-900 dark:text-white uppercase tracking-tight">
                  {mode.kind === "indicator" ? "Geen indicators gevonden" : t?.common?.noAssetsFound}
                </div>
                <div className="text-xs font-bold text-slate-400 mt-1">
                  {mode.kind === "indicator" ? "Probeer RSI, MA 200 of een ander technisch signaal." : t?.common?.tryAnotherAsset}
                </div>
              </div>
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>

      <IndicatorConfigModal
        isOpen={Boolean(pendingIndicator)}
        category={pendingIndicator?.category}
        indicator={pendingIndicator?.indicatorName}
        assetSymbol={activeSymbol}
        mode="add"
        onClose={() => setPendingIndicator(null)}
        onSubmitAction={async ({ category, indicator, assetSymbol }) => {
          const encodedSymbol = encodeURIComponent(assetSymbol);
          const encodedIndicator = encodeURIComponent(indicator);
          const navigationNonce = Date.now();

          if (category === "technical") {
            await technicalDataAdd(indicator, assetSymbol);
            return;
          }

          if (category === "macro") {
            await macroDataAdd(indicator);
            return;
          }

          if (category === "market") {
            await marketIndicatorAdd(indicator, assetSymbol);
          }
        }}
        onCompleted={({ category, indicator, assetSymbol }) => {
          const encodedSymbol = encodeURIComponent(assetSymbol);
          const encodedIndicator = encodeURIComponent(indicator);
          const navigationNonce = Date.now();

          if (category === "technical") {
            router.push(
              `/technical?symbol=${encodedSymbol}&step=technical&technicalIndicator=${encodedIndicator}&indicatorAction=select&indicatorNonce=${navigationNonce}`,
              { scroll: false }
            );
            return;
          }

          if (category === "macro") {
            router.push(
              `/macro?symbol=${encodedSymbol}&step=macro&macroIndicator=${encodedIndicator}&indicatorAction=select&indicatorNonce=${navigationNonce}`,
              { scroll: false }
            );
            return;
          }

          if (category === "market") {
            router.push(
              `/market?symbol=${encodedSymbol}&step=market&marketIndicator=${encodedIndicator}&indicatorAction=select&indicatorNonce=${navigationNonce}`,
              { scroll: false }
            );
          }
        }}
      />
    </div>
  );
}
