"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Check, Coins, Sparkles } from "lucide-react";
import { useTranslation } from "@/app/providers/I18nProvider";
import { useAsset } from "@/app/providers/AssetProvider";
import OnboardingBanner from "@/components/onboarding/OnboardingBanner";
import { useOnboarding } from "@/hooks/useOnboarding";
import { useWatchlist } from "@/hooks/useWatchlist";
import { updateAssistantPreferences } from "@/lib/api/ai";
import { initializeAsset } from "@/lib/api/market";
import {
  buildOnboardingAssetPreferencePatch,
  getSupportedOnboardingAssets,
  normalizeOnboardingAsset,
} from "@/lib/onboardingAsset";

const ASSET_LABELS = {
  BTC: "Bitcoin",
  ETH: "Ethereum",
  SOL: "Solana",
  ADA: "Cardano",
  DOT: "Polkadot",
};

export default function OnboardingAssetPage() {
  const router = useRouter();
  const { t } = useTranslation();
  const { completeStep, saving } = useOnboarding();
  const { setSelectedAsset, addAsset } = useAsset();
  const { add, isInWatchlist } = useWatchlist();
  const [selectedAsset, setSelectedAssetChoice] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const copy = t?.traderProfile?.assetOnboardingStep || {};
  const assets = useMemo(() => getSupportedOnboardingAssets(), []);

  const handleSelect = (symbol) => {
    setSelectedAssetChoice(symbol);
    setError(null);
  };

  const handleSubmit = async () => {
    const normalizedAsset = normalizeOnboardingAsset(selectedAsset);
    if (!normalizedAsset) {
      setError(copy.validationError);
      return;
    }

    try {
      setSubmitting(true);
      setError(null);

      await updateAssistantPreferences(buildOnboardingAssetPreferencePatch(normalizedAsset));
      setSelectedAsset(normalizedAsset);
      addAsset(normalizedAsset);

      if (!isInWatchlist(normalizedAsset)) {
        await add(normalizedAsset);
      }

      await initializeAsset(normalizedAsset).catch(() => null);
      await completeStep("asset");
      router.push(`/onboarding?onboarding=1&step=asset&symbol=${encodeURIComponent(normalizedAsset)}`);
    } catch (err) {
      console.error("Onboarding asset opslaan mislukt", err);
      setError(copy.saveError);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-5xl py-8">
      <OnboardingBanner step="asset" />

      <div className="mb-10 rounded-3xl border border-slate-200 bg-white p-8 shadow-sm">
        <div className="flex flex-col gap-6 md:flex-row md:items-start md:justify-between">
          <div className="max-w-2xl">
            <div className="mb-3 flex items-center gap-3">
              <div className="rounded-2xl bg-blue-50 p-4 text-blue-600">
                <Coins className="h-6 w-6" />
              </div>
              <div>
                <div className="text-[10px] font-black uppercase tracking-[0.25em] text-blue-600">
                  {copy.stepNumber}
                </div>
                <h1 className="text-3xl font-black tracking-tight text-slate-900">
                  {copy.title}
                </h1>
              </div>
            </div>
            <p className="text-sm font-medium leading-relaxed text-slate-500">
              {copy.description}
            </p>
          </div>

          <div className="rounded-2xl border border-blue-100 bg-blue-50 px-4 py-3 text-sm font-semibold leading-relaxed text-slate-700">
            <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-blue-600">
              <Sparkles size={14} />
              {copy.finnSaysLabel}
            </div>
            <p className="mt-2 max-w-sm">{copy.finnSaysBody}</p>
          </div>
        </div>
      </div>

      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="mb-4">
          <h2 className="text-lg font-black tracking-tight text-slate-900">{copy.assetGroupTitle}</h2>
          <p className="mt-1 text-sm font-medium leading-relaxed text-slate-500">{copy.assetGroupSubtitle}</p>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {assets.map((asset) => {
            const active = selectedAsset === asset;
            return (
              <button
                key={asset}
                type="button"
                onClick={() => handleSelect(asset)}
                className={`rounded-3xl border p-5 text-left transition ${
                  active
                    ? "border-blue-600 bg-blue-600 text-white shadow-lg shadow-blue-500/20"
                    : "border-slate-200 bg-slate-50 text-slate-800 hover:border-blue-200 hover:bg-white"
                }`}
              >
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="text-[10px] font-black uppercase tracking-[0.25em] opacity-80">
                      {copy.assetLabel}
                    </div>
                    <div className="mt-2 text-2xl font-black tracking-tight">{asset}</div>
                    <div className={`mt-1 text-sm font-semibold ${active ? "text-white/80" : "text-slate-500"}`}>
                      {ASSET_LABELS[asset] || asset}
                    </div>
                  </div>
                  {active ? <Check className="h-5 w-5" /> : null}
                </div>
              </button>
            );
          })}
        </div>
      </section>

      {error ? (
        <div className="mt-6 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">
          {error}
        </div>
      ) : null}

      <div className="mt-8 flex flex-col gap-4 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm md:flex-row md:items-center md:justify-between">
        <p className="text-sm font-medium leading-relaxed text-slate-500">{copy.footer}</p>
        <button
          type="button"
          onClick={handleSubmit}
          disabled={!selectedAsset || saving || submitting}
          className="inline-flex items-center justify-center gap-2 rounded-2xl bg-blue-600 px-5 py-3 text-[11px] font-black uppercase tracking-[0.18em] text-white shadow-lg shadow-blue-500/20 transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting || saving ? copy.saving : copy.saveAndContinue}
          <ArrowRight size={14} />
        </button>
      </div>
    </div>
  );
}
