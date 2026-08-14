"use client";

import { useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { CheckCircle2, Search, Sparkles } from "lucide-react";

import { useTranslation } from "@/app/providers/I18nProvider";
import { useAsset } from "@/app/providers/AssetProvider";
import OnboardingBanner from "@/components/onboarding/OnboardingBanner";
import { useOnboarding } from "@/hooks/useOnboarding";
import { useWatchlist } from "@/hooks/useWatchlist";
import { searchAssets } from "@/lib/api/assets";
import { updateAssistantPreferences } from "@/lib/api/ai";
import { initializeAsset } from "@/lib/api/market";
import {
  getMacroIndicatorNames,
  syncMacroPreferences,
  updateMacroPreferences,
} from "@/lib/api/macro";
import {
  getMarketIndicatorNames,
  syncMarketPreferences,
  updateMarketPreferences,
} from "@/lib/api/market";
import {
  getIndicatorNames as getTechnicalIndicatorNames,
  syncTechnicalPreferences,
  updateTechnicalPreferences,
} from "@/lib/api/technical";
import { buildOnboardingAssetPreferencePatch, normalizeOnboardingAsset } from "@/lib/onboardingAsset";

const ASSET_CLASS_LABELS = {
  crypto: "Crypto",
  stock: "Stock",
};

function normalizeCatalogItems(items) {
  if (!Array.isArray(items)) return [];

  return items
    .map((item) => {
      if (typeof item === "string") {
        const name = item.trim();
        return name ? { name, display_name: name } : null;
      }

      if (item && typeof item === "object") {
        const rawName = typeof item.name === "string" ? item.name : "";
        const rawDisplayName = typeof item.display_name === "string" ? item.display_name : "";
        const name = rawName.trim() || rawDisplayName.trim();
        if (!name) return null;

        return {
          name,
          display_name: rawDisplayName.trim() || name,
        };
      }

      return null;
    })
    .filter(Boolean);
}

function normalizeName(value) {
  return String(value || "").trim().toLowerCase();
}

function getOptionLabel(option) {
  return String(option?.display_name || option?.name || "").trim();
}

function isDuplicateIndicatorError(err) {
  const status = Number(err?.status);
  const body = String(err?.body || "");
  return status === 409 || /al toegevoegd|already added|already exists|conflict/i.test(body);
}

function buildSinglePreferencePayload(option) {
  return option?.name
    ? [{ indicator: option.name, priority: 1 }]
    : [];
}

function SearchResultList({
  query,
  loading,
  results,
  onSelect,
  emptyLabel,
  selectLabel,
  marketFallback,
  assetClasses,
}) {
  if (!query.trim()) return null;

  return (
    <div className="absolute left-0 right-0 top-[calc(100%+8px)] z-20 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-[0_18px_40px_-24px_rgba(15,23,42,0.22)]">
      <div className="max-h-[320px] overflow-y-auto p-2">
        {loading ? (
          <div className="px-3 py-3 text-sm font-semibold text-slate-500">Loading…</div>
        ) : results.length > 0 ? (
          <div className="grid gap-1.5">
            {results.map((item) => (
              <button
                key={`${item.symbol}-${item.asset_class || "asset"}`}
                type="button"
                onClick={() => void onSelect(item)}
                className="group flex w-full items-center justify-between gap-3 rounded-xl px-3 py-2.5 text-left transition hover:bg-slate-50"
              >
                <div className="min-w-0 flex items-center gap-3">
                  <div className="text-sm font-black tracking-tight text-slate-950">{item.symbol}</div>
                  <div className="truncate text-sm font-semibold text-slate-700">{item.display_name}</div>
                  <div className="hidden text-[11px] font-bold uppercase tracking-[0.18em] text-slate-400 sm:block">
                    {item.exchange || marketFallback}
                  </div>
                  <span className="shrink-0 rounded-full border border-slate-200 bg-slate-50 px-2 py-1 text-[9px] font-black uppercase tracking-[0.16em] text-slate-600">
                    {assetClasses?.[item.asset_class] || ASSET_CLASS_LABELS[item.asset_class] || item.asset_class}
                  </span>
                </div>
                <span className="text-[10px] font-black uppercase tracking-[0.18em] text-blue-600">
                  {selectLabel}
                </span>
              </button>
            ))}
          </div>
        ) : (
          <div className="px-3 py-3 text-sm font-semibold text-slate-500">{emptyLabel}</div>
        )}
      </div>
    </div>
  );
}

function SelectedAssetCard({ asset, onReset, actionLabel }) {
  if (!asset) return null;

  return (
    <div className="rounded-2xl border border-blue-100 bg-blue-50/70 px-4 py-3">
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0 flex items-center gap-3">
          <div className="text-base font-black tracking-tight text-slate-950">{asset.symbol}</div>
          <div className="truncate text-sm font-semibold text-slate-700">{asset.display_name}</div>
          <div className="hidden text-[11px] font-bold uppercase tracking-[0.18em] text-slate-400 sm:block">
            {asset.exchange || "Market"}
          </div>
          <span className="shrink-0 rounded-full border border-blue-200 bg-white px-2 py-1 text-[9px] font-black uppercase tracking-[0.16em] text-blue-700">
            {ASSET_CLASS_LABELS[asset.asset_class] || asset.asset_class}
          </span>
        </div>

        <button
          type="button"
          onClick={onReset}
          className="shrink-0 rounded-full border border-slate-200 bg-white px-4 py-2 text-[11px] font-black uppercase tracking-[0.18em] text-slate-700 transition hover:border-blue-200 hover:text-blue-700"
        >
          {actionLabel}
        </button>
      </div>
    </div>
  );
}

function SelectedIndicatorCard({ item, typeLabel, actionLabel, onReset, disabled }) {
  if (!item) return null;

  return (
    <div className="rounded-2xl border border-blue-100 bg-blue-50/70 px-4 py-3">
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="truncate text-base font-black tracking-tight text-slate-950">
              {getOptionLabel(item)}
            </span>
            <span className="rounded-full border border-blue-200 bg-white px-2 py-1 text-[9px] font-black uppercase tracking-[0.16em] text-blue-700">
              {typeLabel}
            </span>
          </div>
        </div>

        <button
          type="button"
          onClick={onReset}
          disabled={disabled}
          className="shrink-0 rounded-full border border-slate-200 bg-white px-4 py-2 text-[11px] font-black uppercase tracking-[0.18em] text-slate-700 transition hover:border-blue-200 hover:text-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {actionLabel}
        </button>
      </div>
    </div>
  );
}

function IndicatorSelector({
  title,
  placeholder,
  query,
  selected,
  options,
  loading,
  saving,
  success,
  typeLabel,
  onQueryChange,
  onSelect,
  onReset,
  selectLabel,
  emptyLabel,
  changeLabel,
  addedLabel,
  isOpen,
  onOpen,
  disabled = false,
}) {
  const showDropdown = !disabled && isOpen && query.trim().length > 0 && !selected;

  return (
    <section className="rounded-[28px] border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="text-base font-black tracking-tight text-slate-900">{title}</h2>
        {success ? (
          <span className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-[10px] font-black uppercase tracking-[0.18em] text-emerald-700">
            <CheckCircle2 size={12} />
            {addedLabel}
          </span>
        ) : null}
      </div>

      <div className="space-y-3">
        <div className="relative">
          <Search size={18} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            onFocus={() => {
              if (!disabled) onOpen();
            }}
            placeholder={placeholder}
            disabled={saving || disabled}
            className="w-full rounded-2xl border border-slate-200 bg-white py-4 pl-11 pr-4 text-sm font-semibold text-slate-900 outline-none transition focus:border-blue-300 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-400"
          />

          {showDropdown ? (
            <div className="absolute left-0 right-0 top-[calc(100%+8px)] z-20 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-[0_18px_40px_-24px_rgba(15,23,42,0.22)]">
              <div className="max-h-[280px] overflow-y-auto p-2">
                {loading ? (
                  <div className="px-3 py-3 text-sm font-semibold text-slate-500">Loading…</div>
                ) : options.length > 0 ? (
                  <div className="grid gap-1.5">
                    {options.map((option) => (
                      <button
                        key={option.name}
                        type="button"
                        onClick={() => onSelect(option)}
                        disabled={saving}
                        className="flex w-full items-center justify-between gap-3 rounded-xl px-3 py-2.5 text-left transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        <div className="min-w-0">
                          <div className="truncate text-sm font-black text-slate-900">
                            {getOptionLabel(option)}
                          </div>
                          {option.display_name && option.display_name !== option.name ? (
                            <div className="truncate text-[11px] font-semibold text-slate-400">
                              {option.name}
                            </div>
                          ) : null}
                        </div>
                        <span className="text-[10px] font-black uppercase tracking-[0.18em] text-blue-600">
                          {selectLabel}
                        </span>
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="px-3 py-3 text-sm font-semibold text-slate-500">{emptyLabel}</div>
                )}
              </div>
            </div>
          ) : null}
        </div>

        <SelectedIndicatorCard
          item={selected}
          typeLabel={typeLabel}
          actionLabel={changeLabel}
          onReset={onReset}
          disabled={saving}
        />
      </div>
    </section>
  );
}

export default function OnboardingAnalysisPage() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { t } = useTranslation();
  const { status, completeStep } = useOnboarding();
  const { setSelectedAsset, addAsset } = useAsset();
  const { add, isInWatchlist } = useWatchlist();

  const copy = t?.traderProfile?.analysisOnboardingStep || {};

  const [catalogLoading, setCatalogLoading] = useState(true);
  const [loadingResults, setLoadingResults] = useState(false);
  const [submittingAsset, setSubmittingAsset] = useState(false);
  const [continuing, setContinuing] = useState(false);
  const [savingKey, setSavingKey] = useState(null);
  const [error, setError] = useState(null);

  const [assetQuery, setAssetQuery] = useState("");
  const [assetResults, setAssetResults] = useState([]);
  const [searchOpen, setSearchOpen] = useState(false);
  const [openSelector, setOpenSelector] = useState(null);
  const [selectedAssetChoice, setSelectedAssetChoice] = useState(null);

  const [marketQuery, setMarketQuery] = useState("");
  const [macroQuery, setMacroQuery] = useState("");
  const [technicalQuery, setTechnicalQuery] = useState("");

  const [marketCatalog, setMarketCatalog] = useState([]);
  const [macroCatalog, setMacroCatalog] = useState([]);
  const [technicalCatalog, setTechnicalCatalog] = useState([]);

  const [selectedMarket, setSelectedMarket] = useState(null);
  const [selectedMacro, setSelectedMacro] = useState(null);
  const [selectedTechnical, setSelectedTechnical] = useState(null);

  const symbol = selectedAssetChoice?.symbol || "";
  const assetDone = Boolean(selectedAssetChoice);
  const marketDone = Boolean(selectedMarket);
  const macroDone = Boolean(selectedMacro);
  const technicalDone = Boolean(selectedTechnical);
  const allDone = assetDone && marketDone && macroDone && technicalDone;

  useEffect(() => {
    if (pathname !== "/onboarding/analysis") return;

    setAssetQuery("");
    setAssetResults([]);
    setSearchOpen(false);
    setOpenSelector(null);
    setSelectedAssetChoice(null);
    setMarketQuery("");
    setMacroQuery("");
    setTechnicalQuery("");
    setSelectedMarket(null);
    setSelectedMacro(null);
    setSelectedTechnical(null);
    setContinuing(false);
    setSavingKey(null);
    setError(null);
  }, [pathname]);

  useEffect(() => {
    let cancelled = false;

    async function loadResults() {
      const normalizedQuery = String(assetQuery || "").trim();
      if (!normalizedQuery || selectedAssetChoice) {
        setAssetResults([]);
        setLoadingResults(false);
        return;
      }

      try {
        setLoadingResults(true);
        const data = await searchAssets(normalizedQuery, {
          assetClasses: ["crypto", "stock"],
          limit: 8,
        });
        if (!cancelled) {
          setAssetResults(Array.isArray(data) ? data : []);
        }
      } catch (err) {
        console.error("Asset search failed", err);
        if (!cancelled) {
          setAssetResults([]);
        }
      } finally {
        if (!cancelled) {
          setLoadingResults(false);
        }
      }
    }

    const timer = window.setTimeout(loadResults, 180);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [assetQuery, selectedAssetChoice]);

  useEffect(() => {
    let cancelled = false;

    async function loadStep() {
      try {
        setCatalogLoading(true);
        setError(null);

        const hasChosenAsset = Boolean(symbol);

        const [marketNames, macroNames, technicalNames] = await Promise.all([
          getMarketIndicatorNames().catch(() => []),
          getMacroIndicatorNames().catch(() => []),
          getTechnicalIndicatorNames().catch(() => []),
        ]);

        if (cancelled) return;

        setMarketCatalog(normalizeCatalogItems(marketNames));
        setMacroCatalog(normalizeCatalogItems(macroNames));
        setTechnicalCatalog(normalizeCatalogItems(technicalNames));

        // Onboarding starts blank on purpose.
        // Existing backend indicators may still exist from earlier attempts,
        // but they should not auto-complete this step for the user.
        setSelectedMarket(null);
        setSelectedMacro(null);
        setSelectedTechnical(null);
      } catch (err) {
        console.error("Failed to load onboarding analysis step", err);
        if (!cancelled) {
          setError(copy.loadError || "Loading the analysis onboarding step failed.");
        }
      } finally {
        if (!cancelled) setCatalogLoading(false);
      }
    }

    loadStep();
    return () => {
      cancelled = true;
    };
  }, [copy.loadError, symbol]);

  const goToPlan = () => {
    if (!symbol || continuing) return;
    setContinuing(true);
    router.push(`/onboarding/plan?onboarding=1&step=plan&symbol=${encodeURIComponent(symbol)}`);
  };

  const filteredMarket = useMemo(() => {
    const normalized = normalizeName(marketQuery);
    if (!normalized) return [];
    return marketCatalog
      .filter(
        (option) =>
          normalizeName(option.name).includes(normalized) ||
          normalizeName(option.display_name).includes(normalized),
      )
      .slice(0, 8);
  }, [marketCatalog, marketQuery]);

  const filteredMacro = useMemo(() => {
    const normalized = normalizeName(macroQuery);
    if (!normalized) return [];
    return macroCatalog
      .filter(
        (option) =>
          normalizeName(option.name).includes(normalized) ||
          normalizeName(option.display_name).includes(normalized),
      )
      .slice(0, 8);
  }, [macroCatalog, macroQuery]);

  const filteredTechnical = useMemo(() => {
    const normalized = normalizeName(technicalQuery);
    if (!normalized) return [];
    return technicalCatalog
      .filter(
        (option) =>
          normalizeName(option.name).includes(normalized) ||
          normalizeName(option.display_name).includes(normalized),
      )
      .slice(0, 8);
  }, [technicalCatalog, technicalQuery]);

  const persistSelectedAsset = async (asset) => {
    const normalizedAsset = normalizeOnboardingAsset(asset?.symbol);
    if (!normalizedAsset || !asset) {
      throw new Error("missing-asset");
    }

    await updateAssistantPreferences(buildOnboardingAssetPreferencePatch(normalizedAsset));
    setSelectedAsset(normalizedAsset);
    addAsset(normalizedAsset);

    if (!isInWatchlist(normalizedAsset)) {
      await add({
        symbol: normalizedAsset,
        asset_class: asset.asset_class,
        display_name: asset.display_name,
        tradingview_symbol: asset.tradingview_symbol,
      });
    }

    await initializeAsset(normalizedAsset).catch(() => null);
    if (!status?.has_asset) {
      await completeStep("asset");
    }
  };

  const handleAssetSelect = async (asset) => {
    try {
      setSubmittingAsset(true);
      setError(null);
      await persistSelectedAsset(asset);
      setSelectedAssetChoice(asset);
      setAssetQuery(asset?.symbol || "");
      setSearchOpen(false);
      setOpenSelector("market");
      setContinuing(false);
    } catch (err) {
      console.error("Onboarding asset select failed", err);
      setError(copy.saveError || "Saving this analysis step failed. Please try again.");
    } finally {
      setSubmittingAsset(false);
    }
  };

  const handleSelectIndicator = async (kind, option) => {
    if (!option?.name) return;

    try {
      setSavingKey(kind);
      setError(null);
      const assetClass = selectedAssetChoice?.asset_class || null;
      const indicators = buildSinglePreferencePayload(option);

      if (kind === "market") {
        await updateMarketPreferences({ symbol, assetClass, indicators });
        await syncMarketPreferences(symbol, { resetExisting: true });
        if (!status?.has_market) await completeStep("market");
        setSelectedMarket(option);
        setMarketQuery("");
        setOpenSelector("macro");
      }

      if (kind === "macro") {
        await updateMacroPreferences({ symbol, assetClass, indicators });
        await syncMacroPreferences(symbol, { resetExisting: true });
        if (!status?.has_macro) await completeStep("macro");
        setSelectedMacro(option);
        setMacroQuery("");
        setOpenSelector("technical");
      }

      if (kind === "technical") {
        await updateTechnicalPreferences({ symbol, assetClass, indicators });
        await syncTechnicalPreferences(symbol, { resetExisting: true });
        if (!status?.has_technical) await completeStep("technical");
        setSelectedTechnical(option);
        setTechnicalQuery("");
        setOpenSelector(null);
      }
    } catch (err) {
      if (isDuplicateIndicatorError(err)) {
        if (kind === "market") {
          setSelectedMarket(option);
          setMarketQuery("");
          setOpenSelector("macro");
          if (!status?.has_market) await completeStep("market");
        }

        if (kind === "macro") {
          setSelectedMacro(option);
          setMacroQuery("");
          setOpenSelector("technical");
          if (!status?.has_macro) await completeStep("macro");
        }

        if (kind === "technical") {
          setSelectedTechnical(option);
          setTechnicalQuery("");
          setOpenSelector(null);
          if (!status?.has_technical) await completeStep("technical");
        }

        return;
      }

      console.error(`Failed to add ${kind} onboarding indicator`, err);
      setError(copy.saveError || "Saving this analysis step failed. Please try again.");
    } finally {
      setSavingKey(null);
    }
  };

  return (
    <div className="mx-auto max-w-5xl py-8">
      <OnboardingBanner step="asset" />

      <div className="mb-10 rounded-3xl border border-slate-200 bg-white p-8 shadow-sm">
        <div className="flex flex-col gap-6 md:flex-row md:items-start md:justify-between">
          <div className="max-w-2xl">
            <div className="text-[10px] font-black uppercase tracking-[0.25em] text-blue-600">
              {copy.stepNumber || "Analysis · 2 of 4"}
            </div>
            <h1 className="mt-3 text-3xl font-black tracking-tight text-slate-900">
              {copy.title || "Add your first analysis base"}
            </h1>
            <p className="mt-4 text-sm font-medium leading-relaxed text-slate-500">
              {(copy.description || "Choose one asset, then add one market, one macro, and one technical indicator.").replace("{symbol}", symbol)}
            </p>
          </div>

          <div className="rounded-2xl border border-blue-100 bg-blue-50 px-4 py-3 text-sm font-semibold leading-relaxed text-slate-700">
            <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-blue-600">
              <Sparkles size={14} />
              {copy.finnSaysLabel || "Finn says"}
            </div>
            <p className="mt-2 max-w-sm">
              {(copy.finnSaysBody || "Keep this step intentionally small. One asset and one indicator per category are enough to build your first real context.").replace("{symbol}", symbol)}
            </p>
          </div>
        </div>
      </div>

      <section className="rounded-[28px] border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4">
          <h2 className="text-base font-black tracking-tight text-slate-900">
            {copy.assetTitle || "Choose your first asset"}
          </h2>
        </div>

        <div className="space-y-4">
          <div className="relative">
            <Search size={18} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              value={assetQuery}
            onChange={(event) => {
              setAssetQuery(event.target.value);
              setError(null);
              setSearchOpen(true);
              setOpenSelector(null);
              setSelectedAssetChoice(null);
              setSelectedMarket(null);
              setSelectedMacro(null);
              setSelectedTechnical(null);
              setMarketQuery("");
              setMacroQuery("");
              setTechnicalQuery("");
            }}
              onFocus={() => setSearchOpen(true)}
              placeholder={copy.assetPlaceholder || "Search BTC, Apple or Microsoft"}
              disabled={submittingAsset}
              className="w-full rounded-2xl border border-slate-200 bg-white py-4 pl-11 pr-4 text-sm font-semibold text-slate-900 outline-none transition focus:border-blue-300 disabled:cursor-not-allowed disabled:bg-slate-50"
            />

            {searchOpen ? (
              <SearchResultList
                query={assetQuery}
                loading={loadingResults}
                results={assetResults}
                onSelect={handleAssetSelect}
                emptyLabel={copy.assetEmptyLabel || "No matching results found."}
                selectLabel={copy.selectLabel || "Select"}
                marketFallback={copy.assetMarketFallback || "Market"}
                assetClasses={copy.assetClasses}
              />
            ) : null}
          </div>

          <SelectedAssetCard
            asset={selectedAssetChoice}
            onReset={() => {
              setSelectedAssetChoice(null);
              setAssetQuery("");
              setSearchOpen(false);
              setOpenSelector(null);
            }}
            actionLabel={copy.assetChangeLabel || "Select asset"}
          />
        </div>
      </section>

      <div className="mt-5 grid gap-5">
        <IndicatorSelector
          title={copy.marketTitle || "1. Market indicator"}
          placeholder={copy.marketPlaceholder || "Search a market indicator"}
          query={marketQuery}
          selected={selectedMarket}
          options={filteredMarket}
          loading={catalogLoading}
          saving={savingKey === "market"}
          success={marketDone}
          typeLabel={copy.marketTypeLabel || "Market"}
          onQueryChange={(value) => {
            setMarketQuery(value);
            setOpenSelector("market");
            setError(null);
          }}
          onSelect={(option) => void handleSelectIndicator("market", option)}
          onReset={() => {
            setSelectedMarket(null);
            setOpenSelector("market");
          }}
          selectLabel={copy.selectLabel || "Select"}
          emptyLabel={copy.emptyLabel || "No matching indicators found."}
          changeLabel={copy.changeLabel || "Select other"}
          addedLabel={copy.addedLabel || "Added"}
          isOpen={openSelector === "market"}
          onOpen={() => setOpenSelector("market")}
          disabled={!assetDone}
        />

        <IndicatorSelector
          title={copy.macroTitle || "2. Macro indicator"}
          placeholder={copy.macroPlaceholder || "Search a macro indicator"}
          query={macroQuery}
          selected={selectedMacro}
          options={filteredMacro}
          loading={catalogLoading}
          saving={savingKey === "macro"}
          success={macroDone}
          typeLabel={copy.macroTypeLabel || "Macro"}
          onQueryChange={(value) => {
            setMacroQuery(value);
            setOpenSelector("macro");
            setError(null);
          }}
          onSelect={(option) => void handleSelectIndicator("macro", option)}
          onReset={() => {
            setSelectedMacro(null);
            setOpenSelector("macro");
          }}
          selectLabel={copy.selectLabel || "Select"}
          emptyLabel={copy.emptyLabel || "No matching indicators found."}
          changeLabel={copy.changeLabel || "Select other"}
          addedLabel={copy.addedLabel || "Added"}
          isOpen={openSelector === "macro"}
          onOpen={() => setOpenSelector("macro")}
          disabled={!assetDone || !marketDone}
        />

        <IndicatorSelector
          title={copy.technicalTitle || "3. Technical indicator"}
          placeholder={copy.technicalPlaceholder || "Search a technical indicator"}
          query={technicalQuery}
          selected={selectedTechnical}
          options={filteredTechnical}
          loading={catalogLoading}
          saving={savingKey === "technical"}
          success={technicalDone}
          typeLabel={copy.technicalTypeLabel || "Technical"}
          onQueryChange={(value) => {
            setTechnicalQuery(value);
            setOpenSelector("technical");
            setError(null);
          }}
          onSelect={(option) => void handleSelectIndicator("technical", option)}
          onReset={() => {
            setSelectedTechnical(null);
            setOpenSelector("technical");
          }}
          selectLabel={copy.selectLabel || "Select"}
          emptyLabel={copy.emptyLabel || "No matching indicators found."}
          changeLabel={copy.changeLabel || "Select other"}
          addedLabel={copy.addedLabel || "Added"}
          isOpen={openSelector === "technical"}
          onOpen={() => setOpenSelector("technical")}
          disabled={!assetDone || !marketDone || !macroDone}
        />
      </div>

      {error ? (
        <div className="mt-6 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">
          {error}
        </div>
      ) : null}

      {allDone ? (
        <div className="mt-6 rounded-[28px] border border-emerald-200 bg-emerald-50/80 p-5">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="text-[10px] font-black uppercase tracking-[0.22em] text-emerald-700">
                {copy.successEyebrow || "Analysis ready"}
              </div>
              <div className="mt-2 text-lg font-black tracking-tight text-slate-950">
                {copy.successTitle || "Your first analysis base is saved"}
              </div>
              <p className="mt-2 text-sm font-semibold text-slate-600">
                {copy.successMessage || "You selected one asset plus one market, macro, and technical indicator. Review the summary below and continue to My Plan when you're ready."}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <span className="rounded-full border border-emerald-200 bg-white px-3 py-1 text-[10px] font-black uppercase tracking-[0.18em] text-emerald-700">
                  {selectedAssetChoice?.symbol}
                </span>
                <span className="rounded-full border border-slate-200 bg-white px-3 py-1 text-[10px] font-black uppercase tracking-[0.18em] text-slate-700">
                  {getOptionLabel(selectedMarket)}
                </span>
                <span className="rounded-full border border-slate-200 bg-white px-3 py-1 text-[10px] font-black uppercase tracking-[0.18em] text-slate-700">
                  {getOptionLabel(selectedMacro)}
                </span>
                <span className="rounded-full border border-slate-200 bg-white px-3 py-1 text-[10px] font-black uppercase tracking-[0.18em] text-slate-700">
                  {getOptionLabel(selectedTechnical)}
                </span>
              </div>
            </div>

            <button
              type="button"
              onClick={goToPlan}
              disabled={continuing}
              className="shrink-0 rounded-full bg-blue-600 px-6 py-3 text-[11px] font-black uppercase tracking-[0.2em] text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {continuing
                ? (copy.continuingLabel || "Opening My Plan…")
                : (copy.continueLabel || "Continue to My Plan")}
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
