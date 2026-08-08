"use client";

import { forwardRef, useEffect, useImperativeHandle, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  ArrowRight,
  BarChart3,
  Bot,
  Check,
  Layers3,
  MessageSquare,
  Search,
  Sparkles,
  Star,
  Workflow,
} from "lucide-react";

import { useAsset } from "@/app/providers/AssetProvider";
import { useActiveSetup } from "@/app/providers/SetupProvider";
import { useTranslation } from "@/app/providers/I18nProvider";
import { useModal } from "@/components/modal/ModalProvider";
import IndicatorConfigModal from "@/components/scoring/IndicatorConfigModal";
import { initializeAsset, getMarketIndicatorNames, marketIndicatorAdd } from "@/lib/api/market";
import { getMacroIndicatorNames, macroDataAdd } from "@/lib/api/macro";
import { getIndicatorNames as getTechnicalIndicatorNames, technicalDataAdd } from "@/lib/api/technical";
import {
  FINN_ASSETS,
  FINN_INDICATOR_MODAL_COMPLETED_EVENT,
  FINN_INDICATOR_MODAL_OPEN_EVENT,
  getDefaultIndicatorCategory,
  matchesCommandQuery,
} from "@/lib/finnCommandSearch";
import { publishWorkspaceRefresh } from "@/lib/workspaceSync";

let indicatorCatalogCache = null;
let indicatorCatalogPromise = null;

async function loadIndicatorCatalog() {
  if (indicatorCatalogCache) return indicatorCatalogCache;
  if (!indicatorCatalogPromise) {
    indicatorCatalogPromise = Promise.all([
      getTechnicalIndicatorNames(),
      getMacroIndicatorNames(),
      getMarketIndicatorNames(),
    ])
      .then(([technical, macro, market]) => {
        indicatorCatalogCache = {
          technical: Array.isArray(technical) ? technical : [],
          macro: Array.isArray(macro) ? macro : [],
          market: Array.isArray(market) ? market : [],
        };
        return indicatorCatalogCache;
      })
      .catch((error) => {
        indicatorCatalogPromise = null;
        throw error;
      });
  }
  return indicatorCatalogPromise;
}

function withVariant(path, variant) {
  if (variant !== "legacy") return path;
  return `${path}${path.includes("?") ? "&" : "?"}variant=legacy`;
}

function commandCopy(locale) {
  const normalized = String(locale || "nl").toLowerCase();
  if (normalized.startsWith("en")) {
    return {
      heading: "Direct actions",
      assets: "Assets",
      indicators: "Indicators",
      pages: "Workspaces",
      askFinn: "Ask FINN",
      askDescription: "Use AI for explanation and context",
      searchAsset: "Search asset",
      addIndicator: "Add indicator",
      openAnalysis: "Open Analysis",
      openPlan: "Open My Plan",
      addTechnical: "Configure for Technical",
      addMacro: "Configure for Macro",
      addMarket: "Configure for Market",
      loading: "Loading indicators...",
      noResults: "No direct actions found",
      noResultsHint: "Ask FINN or try another search term.",
      added: "added",
      failed: "Could not open this action.",
    };
  }
  if (normalized.startsWith("de")) {
    return {
      heading: "Direkte Aktionen",
      assets: "Assets",
      indicators: "Indikatoren",
      pages: "Arbeitsbereiche",
      askFinn: "FINN fragen",
      askDescription: "KI für Erklärung und Kontext verwenden",
      searchAsset: "Asset suchen",
      addIndicator: "Indikator hinzufügen",
      openAnalysis: "Analyse öffnen",
      openPlan: "Mein Plan öffnen",
      addTechnical: "Für Technik konfigurieren",
      addMacro: "Für Makro konfigurieren",
      addMarket: "Für Markt konfigurieren",
      loading: "Indikatoren werden geladen...",
      noResults: "Keine direkte Aktion gefunden",
      noResultsHint: "Frage FINN oder versuche einen anderen Suchbegriff.",
      added: "hinzugefügt",
      failed: "Diese Aktion konnte nicht geöffnet werden.",
    };
  }
  return {
    heading: "Directe acties",
    assets: "Assets",
    indicators: "Indicatoren",
    pages: "Werkruimtes",
    askFinn: "Vraag FINN",
    askDescription: "Gebruik AI voor uitleg en context",
    searchAsset: "Asset zoeken",
    addIndicator: "Indicator toevoegen",
    openAnalysis: "Open Analyse",
    openPlan: "Open Mijn Plan",
    addTechnical: "Configureren voor Technisch",
    addMacro: "Configureren voor Macro",
    addMarket: "Configureren voor Markt",
    loading: "Indicatoren laden...",
    noResults: "Geen directe actie gevonden",
    noResultsHint: "Vraag FINN of probeer een andere zoekterm.",
    added: "toegevoegd",
    failed: "Deze actie kon niet worden geopend.",
  };
}

const FinnCommandCenter = forwardRef(function FinnCommandCenter(
  { isOpen, onAskFinn, onClose, onQueryChange, query, request, watchlist },
  ref
) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { locale } = useTranslation();
  const copy = commandCopy(locale);
  const { selectedAsset, setSelectedAsset } = useAsset();
  const { setActiveSetup, setFocusedBotId } = useActiveSetup();
  const { showSnackbar } = useModal();
  const [mode, setMode] = useState({ kind: "all", category: null });
  const [catalog, setCatalog] = useState(indicatorCatalogCache || { technical: [], macro: [], market: [] });
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [pendingIndicator, setPendingIndicator] = useState(null);
  const [activeIndex, setActiveIndex] = useState(0);

  const activeSymbol = searchParams.get("symbol")?.toUpperCase() || selectedAsset || "BTC";
  const activeVariant = searchParams.get("variant") === "legacy" ? "legacy" : "v3";
  const hasQuery = Boolean(String(query || "").trim());

  useEffect(() => {
    if (!isOpen) return;
    setCatalogLoading(true);
    loadIndicatorCatalog()
      .then(setCatalog)
      .catch((error) => console.error("Failed to load FINN command indicators:", error))
      .finally(() => setCatalogLoading(false));
  }, [isOpen]);

  useEffect(() => {
    if (!request?.nonce) return;
    if (!request?.query) {
      onQueryChange("");
    }
    setMode(
      request.mode === "indicator"
        ? { kind: "indicator", category: request.category || getDefaultIndicatorCategory(pathname) }
        : request.mode === "asset"
          ? { kind: "asset", category: null }
          : { kind: "all", category: null }
    );
    setActiveIndex(0);
  }, [pathname, request]);

  useEffect(() => {
    const openIndicator = (event) => {
      const detail = event?.detail || {};
      if (!detail.indicatorName) return;
      setPendingIndicator({
        category: detail.category || "technical",
        indicatorName: detail.indicatorName,
        title: detail.title || detail.indicatorName,
        source: detail.source || "finn",
      });
    };
    window.addEventListener(FINN_INDICATOR_MODAL_OPEN_EVENT, openIndicator);
    return () => window.removeEventListener(FINN_INDICATOR_MODAL_OPEN_EVENT, openIndicator);
  }, []);

  useEffect(() => setActiveIndex(0), [mode, query]);

  const workflows = useMemo(
    () => [
      { id: "analysis", title: locale?.startsWith("nl") ? "Analyse" : "Analysis", subtitle: copy.pages, href: `/asset?symbol=${activeSymbol}`, icon: BarChart3 },
      { id: "portfolio", title: "Portfolio", subtitle: copy.pages, href: "/portfolio", icon: Layers3 },
      { id: "plan", title: locale?.startsWith("en") ? "My Plan" : locale?.startsWith("de") ? "Mein Plan" : "Mijn Plan", subtitle: copy.pages, href: `/setup?symbol=${activeSymbol}`, icon: Workflow },
      { id: "automation", title: locale?.startsWith("nl") ? "Automatisering" : locale?.startsWith("de") ? "Automatisierung" : "Automation", subtitle: copy.pages, href: `/bot?symbol=${activeSymbol}`, icon: Bot },
      { id: "reflection", title: locale?.startsWith("en") ? "Reflection" : locale?.startsWith("de") ? "Reflexion" : "Reflectie", subtitle: copy.pages, href: `/report?symbol=${activeSymbol}`, icon: Check },
    ],
    [activeSymbol, copy.pages, locale]
  );

  const assetResults = useMemo(() => {
    if (mode.kind === "indicator") return [];
    if (!hasQuery && mode.kind !== "asset") return [];
    return FINN_ASSETS.filter((asset) => matchesCommandQuery(`${asset.symbol} ${asset.name}`, query)).map((asset) => ({
      id: `asset:${asset.symbol}`,
      type: "asset",
      title: asset.symbol,
      subtitle: asset.name,
      asset,
      icon: Search,
    }));
  }, [hasQuery, mode.kind, query]);

  const workflowResults = useMemo(() => {
    if (mode.kind !== "all" || !hasQuery) return [];
    return workflows
      .filter((workflow) => matchesCommandQuery(`${workflow.id} ${workflow.title} ${workflow.subtitle}`, query))
      .map((workflow) => ({ ...workflow, type: "workflow" }));
  }, [hasQuery, mode.kind, query, workflows]);

  const indicatorResults = useMemo(() => {
    if (mode.kind === "asset") return [];
    if (!hasQuery && mode.kind !== "indicator") return [];
    const sources = [
      { key: "technical", label: copy.addTechnical, values: catalog.technical },
      { key: "macro", label: copy.addMacro, values: catalog.macro },
      { key: "market", label: copy.addMarket, values: catalog.market },
    ].filter((source) => !mode.category || source.key === mode.category);

    return sources
      .flatMap((source) =>
        source.values
          .filter((indicator) => matchesCommandQuery(`${indicator?.display_name || ""} ${indicator?.label || ""} ${indicator?.name || ""}`, query))
          .map((indicator) => ({
            id: `indicator:${source.key}:${indicator.name}`,
            type: "indicator",
            title: indicator.display_name || indicator.label || indicator.name,
            subtitle: source.label,
            category: source.key,
            indicatorName: indicator.name,
            icon: Sparkles,
          }))
      )
      .slice(0, 12);
  }, [catalog, copy.addMacro, copy.addMarket, copy.addTechnical, hasQuery, mode.category, mode.kind, query]);

  const directResults = useMemo(
    () => [...assetResults, ...workflowResults, ...indicatorResults],
    [assetResults, indicatorResults, workflowResults]
  );
  const selectableResults = useMemo(
    () => (hasQuery ? [...directResults, { id: "ask-finn", type: "ask", title: `${copy.askFinn}: “${query.trim()}”`, subtitle: copy.askDescription, icon: MessageSquare }] : directResults),
    [copy.askDescription, copy.askFinn, directResults, hasQuery, query]
  );

  const closeCommand = () => {
    onQueryChange("");
    setMode({ kind: "all", category: null });
  };

  const selectResult = async (result) => {
    if (!result) return;
    if (result.type === "ask") {
      onAskFinn();
      return;
    }
    if (result.type === "asset") {
      const symbol = result.asset.symbol;
      setActiveSetup(null);
      setFocusedBotId(null);
      setSelectedAsset(symbol);
      initializeAsset(symbol).catch((error) => console.error("Asset initialization failed:", error));
      router.push(withVariant(`/asset?symbol=${encodeURIComponent(symbol)}`, activeVariant));
      closeCommand();
      onClose();
      return;
    }
    if (result.type === "workflow") {
      router.push(withVariant(result.href, activeVariant));
      closeCommand();
      onClose();
      return;
    }
    if (result.type === "indicator") {
      setPendingIndicator({
        category: result.category,
        indicatorName: result.indicatorName,
        title: result.title,
        source: "finn",
      });
    }
  };

  useImperativeHandle(ref, () => ({
    openAssetSearch() {
      setMode({ kind: "asset", category: null });
      setActiveIndex(0);
    },
    openIndicatorSearch() {
      setMode({ kind: "indicator", category: getDefaultIndicatorCategory(pathname) });
      setActiveIndex(0);
    },
    handleKeyDown(event) {
      if (event.key === "ArrowDown" && selectableResults.length > 0) {
        event.preventDefault();
        setActiveIndex((current) => (current + 1) % selectableResults.length);
        return true;
      }
      if (event.key === "ArrowUp" && selectableResults.length > 0) {
        event.preventDefault();
        setActiveIndex((current) => (current - 1 + selectableResults.length) % selectableResults.length);
        return true;
      }
      if (event.key === "Enter" && selectableResults.length > 0) {
        event.preventDefault();
        selectResult(selectableResults[activeIndex] || selectableResults[0]);
        return true;
      }
      if (event.key === "Escape" && (hasQuery || mode.kind !== "all")) {
        event.preventDefault();
        closeCommand();
        return true;
      }
      return false;
    },
    submitPrimary() {
      if (selectableResults.length === 0) return false;
      selectResult(selectableResults[activeIndex] || selectableResults[0]);
      return true;
    },
  }));

  return (
    <>
      {(hasQuery || mode.kind !== "all") && (
        <div className="mb-3 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-lg shadow-slate-900/5 dark:border-slate-800 dark:bg-slate-950/95">
          <div className="max-h-[330px] overflow-y-auto p-2">
            {catalogLoading && mode.kind === "indicator" && indicatorResults.length === 0 ? (
              <div className="px-4 py-6 text-center text-xs font-semibold text-slate-400">{copy.loading}</div>
            ) : selectableResults.length > 0 ? selectableResults.map((result, index) => {
              const Icon = result.icon || ArrowRight;
              const isActive = index === activeIndex;
              return (
                <div key={result.id} role="button" tabIndex={0} onMouseEnter={() => setActiveIndex(index)} onClick={() => selectResult(result)} className={`flex cursor-pointer items-center justify-between gap-3 rounded-xl px-3 py-3 transition ${isActive ? "bg-blue-50 dark:bg-blue-950/30" : "hover:bg-slate-50 dark:hover:bg-slate-900"}`}>
                  <div className="flex min-w-0 items-center gap-3">
                    <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${result.type === "ask" ? "bg-slate-900 text-white dark:bg-blue-600" : "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-300"}`}>
                      {result.type === "asset" ? <span className="font-black">{result.asset.icon}</span> : <Icon size={16} />}
                    </span>
                    <span className="min-w-0">
                      <span className="block truncate text-xs font-black text-slate-900 dark:text-slate-100">{result.title}</span>
                      <span className="block truncate text-[11px] font-semibold text-slate-400">{result.subtitle}</span>
                    </span>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    {result.type === "asset" ? (
                      <button type="button" aria-label={`${result.title} watchlist`} onClick={(event) => {
                        event.stopPropagation();
                        const symbol = result.asset.symbol;
                        const action = watchlist.isInWatchlist(symbol) ? watchlist.remove(symbol) : watchlist.add(symbol);
                        Promise.resolve(action).then(() => initializeAsset(symbol).catch(() => null));
                      }} className={`rounded-lg p-2 ${watchlist.isInWatchlist(result.asset.symbol) ? "text-amber-400" : "text-slate-300 hover:text-amber-400"}`}>
                        <Star size={15} fill={watchlist.isInWatchlist(result.asset.symbol) ? "currentColor" : "none"} />
                      </button>
                    ) : null}
                    <ArrowRight size={14} className="text-slate-300" />
                  </div>
                </div>
              );
            }) : (
              <div className="px-4 py-7 text-center">
                <div className="text-xs font-black text-slate-700 dark:text-slate-200">{copy.noResults}</div>
                <div className="mt-1 text-[11px] font-medium text-slate-400">{copy.noResultsHint}</div>
              </div>
            )}
          </div>
        </div>
      )}

      <IndicatorConfigModal
        isOpen={Boolean(pendingIndicator)}
        category={pendingIndicator?.category}
        indicator={pendingIndicator?.indicatorName}
        assetSymbol={activeSymbol}
        mode="add"
        showSuccessSnackbar={false}
        onClose={() => setPendingIndicator(null)}
        onSubmitAction={async ({ category, indicator, assetSymbol }) => {
          if (category === "technical") return technicalDataAdd(indicator, assetSymbol);
          if (category === "macro") return macroDataAdd(indicator, assetSymbol);
          if (category === "market") return marketIndicatorAdd(indicator, assetSymbol);
        }}
        onCompleted={({ category, indicator, assetSymbol }) => {
          const params = new URLSearchParams({
            symbol: assetSymbol,
            context: category,
            indicatorNonce: String(Date.now()),
          });

          window.dispatchEvent(new CustomEvent(FINN_INDICATOR_MODAL_COMPLETED_EVENT, {
            detail: { category, indicator, assetSymbol, source: pendingIndicator?.source || "finn" },
          }));
          publishWorkspaceRefresh({
            symbol: assetSymbol,
            category,
            reason: "indicator_added",
          });
          router.push(withVariant(`/asset?${params.toString()}`, activeVariant), { scroll: false });
          setPendingIndicator(null);
          onQueryChange("");
          showSnackbar(`${String(indicator).toUpperCase()} ${copy.added}.`, "success");
        }}
      />
    </>
  );
});

export default FinnCommandCenter;
